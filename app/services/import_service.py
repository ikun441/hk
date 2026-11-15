import hashlib
import re
from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from openpyxl import load_workbook, Workbook
from openpyxl.utils.exceptions import InvalidFileException
from xml.etree.ElementTree import ParseError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ..models import ImportBatch, Customer, Message
from ..schemas import MessageIn
from ..auth import get_customer, audit

HEADERS = ['客户ID或企业名称','消息时间','说话人','消息内容','来源备注']
SPEAKERS = {'客户':'customer','员工':'employee','customer':'customer','employee':'employee'}

def fingerprint(customer_id, message):
    return hashlib.sha256(f'{customer_id}|{message.sent_at.isoformat()}|{message.speaker}|{message.content.strip()}'.encode()).hexdigest()

def insert_message(db, customer, user, data, batch_id=None):
    fp = fingerprint(customer.id, data)
    if db.scalar(select(Message.id).where(Message.fingerprint == fp)):
        return None
    try:
        with db.begin_nested():
            message = Message(customer_id=customer.id, batch_id=batch_id, created_by=user.id, fingerprint=fp, **data.model_dump())
            db.add(message)
            db.flush()
        if not customer.last_followup_at or data.sent_at > customer.last_followup_at:
            customer.last_followup_at = data.sent_at
        return message
    except IntegrityError:
        # A concurrent import may have inserted this exact fingerprint.
        if db.scalar(select(Message.id).where(Message.fingerprint == fp)):
            return None
        raise

def validate_row(db, user, row):
    output = {k:row.get(k,'') for k in ['row','customer_id','sent_at','speaker','content','source']}
    try:
        if any(isinstance(row.get(k), str) and row[k].startswith('=') for k in ['customer_id','sent_at','speaker','content','source']):
            raise ValueError('不接受公式内容，请人工修正为普通文本')
        customer_id = int(row.get('customer_id'))
        customer = get_customer(db, user, customer_id, write=True)
        stamp = row.get('sent_at')
        if isinstance(stamp, str):
            if not re.match(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}', stamp):
                raise ValueError('时间须包含日期和小时分钟')
            stamp = datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if not isinstance(stamp, datetime):
            raise ValueError('时间无效')
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        speaker = SPEAKERS.get(str(row.get('speaker','')).strip())
        if not speaker:
            raise ValueError('说话人只能是客户或员工')
        data = MessageIn(speaker=speaker, sent_at=stamp, content=row.get('content') or '', source=str(row.get('source') or 'import'))
        output.update(customer_id=customer.id, sent_at=data.sent_at.isoformat()+'Z', speaker=data.speaker, content=data.content, source=data.source)
        output['error'] = ''
        output['duplicate'] = bool(db.scalar(select(Message.id).where(Message.fingerprint == fingerprint(customer.id,data))))
        return output, customer, data
    except (ValueError, TypeError, HTTPException) as exc:
        output['error'] = exc.detail if isinstance(exc, HTTPException) else str(exc)[:500]
        output['duplicate'] = False
        return output, None, None

def create_preview(db, user, rows, source):
    if not rows or len(rows)>2000:
        raise HTTPException(422, '每批需 1–2000 行')
    checked = [validate_row(db,user,r)[0] if not r.get('error') else r for r in rows]
    batch = ImportBatch(id=str(uuid4()),user_id=user.id,source=source,rows=checked)
    db.add(batch)
    audit(db,user,'import.preview',batch.id,{'rows':len(rows),'source':source})
    db.commit()
    return {'id':batch.id,'status':batch.status,'rows':checked}

def text_rows(customer_id, text):
    rows=[]
    pattern = re.compile(r'^\[?(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)\]?\s+(客户|员工|customer|employee)\s*[:：]\s*(.*)$')
    for i,line in enumerate(text.splitlines(),1):
        if not line.strip():
            continue
        match = pattern.match(line.strip())
        row={'row':i,'customer_id':customer_id,'sent_at':'','speaker':'','content':line,'source':'text'}
        if match:
            row.update(sent_at=match[1],speaker=SPEAKERS[match[2]],content=match[3])
        else:
            row['error']='格式不明确，请修正时间、说话人和正文后确认'
        rows.append(row)
    return rows

def excel_rows(db, user, content):
    import zipfile
    try:
        with zipfile.ZipFile(BytesIO(content)) as z:
            if sum(i.file_size for i in z.infolist()) > 40*1024*1024:
                raise ValueError('解压后文件过大')
        workbook=load_workbook(BytesIO(content), read_only=True, data_only=False)
        sheet=workbook.active
        values=sheet.iter_rows(values_only=True)
        header=next(values,None)
        if not header or list(header[:5]) != HEADERS:
            raise ValueError('模板表头不匹配，请下载并使用系统模板')
        rows=[]
        for i,values_row in enumerate(values,2):
            if not any(v is not None for v in values_row):
                continue
            if len(rows)>=2000:
                raise ValueError('每批最多 2000 行')
            vals=list(values_row[:5])+[None]*5
            reference, stamp, speaker, body, source=vals[:5]
            row={'row':i,'customer_id':'','sent_at':stamp.isoformat() if isinstance(stamp,datetime) else str(stamp or ''),'speaker':str(speaker or ''),'content':str(body or ''),'source':str(source or 'excel')}
            if any(isinstance(v,str) and v.startswith('=') for v in vals[:5]):
                row['error']='不接受公式单元格，请粘贴为值'
            try:
                if isinstance(reference,(int,float)) or str(reference).isdigit():
                    if isinstance(reference,bool) or (isinstance(reference,float) and not reference.is_integer()):
                        raise ValueError('客户 ID 必须为正整数')
                    cid=int(reference)
                    get_customer(db,user,cid,write=True)
                else:
                    # Resolve only names visible to this user; never reveal hidden records.
                    from ..auth import customer_scope
                    matches=list(db.scalars(select(Customer.id).where(Customer.name==str(reference or ''), Customer.archived.is_(False), customer_scope(user))))
                    if len(matches)!=1:
                        raise ValueError('客户名称不存在、无权限或同名歧义，请改用客户ID')
                    cid=matches[0]
                row['customer_id']=cid
            except (ValueError, HTTPException) as exc:
                row['error']=exc.detail if isinstance(exc,HTTPException) else str(exc)
            rows.append(row)
        workbook.close()
        return rows
    except (ValueError, zipfile.BadZipFile, KeyError, StopIteration, OSError, InvalidFileException, ParseError, TypeError) as exc:
        raise HTTPException(422, f'Excel 解析失败：{exc}') from None

def template_bytes():
    book=Workbook()
    sheet=book.active
    sheet.title='聊天消息'
    sheet.append(HEADERS)
    for column,width in zip('ABCDE',[24,26,16,70,24]):
        sheet.column_dimensions[column].width=width
    sheet.freeze_panes='A2'
    out=BytesIO()
    book.save(out)
    return out.getvalue()
