import csv
from io import StringIO
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from sqlalchemy import update
from ..db import get_db
from ..models import ImportBatch
from ..schemas import TextImportIn, ConfirmIn
from ..auth import current_user, writer, get_customer, audit
from ..services.import_service import create_preview, text_rows, excel_rows, template_bytes, validate_row, insert_message

router=APIRouter(prefix='/api/imports',tags=['聊天导入'])

def own_batch(db,user,batch_id):
    batch=db.get(ImportBatch,batch_id)
    if not batch or batch.user_id!=user.id:
        raise HTTPException(404,'导入批次不存在')
    return batch

@router.get('/template')
def template(user=Depends(current_user),db=Depends(get_db)):
    writer(user)
    audit(db,user,'import.template_export')
    db.commit()
    return Response(template_bytes(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=chat-template.xlsx'})

@router.post('/text')
def text(data:TextImportIn,user=Depends(current_user),db=Depends(get_db)):
    get_customer(db,user,data.customer_id,write=True)
    return create_preview(db,user,text_rows(data.customer_id,data.text),'text')

@router.post('/excel')
def excel(file:UploadFile=File(...),user=Depends(current_user),db=Depends(get_db)):
    writer(user)
    if not file.filename or not file.filename.lower().endswith('.xlsx'):
        raise HTTPException(422,'仅支持 .xlsx 文件')
    content=file.file.read(5*1024*1024+1)
    if len(content)>5*1024*1024:
        raise HTTPException(413,'文件不能超过 5MB')
    return create_preview(db,user,excel_rows(db,user,content),'excel')

@router.get('/{batch_id}')
def get_batch(batch_id:str,user=Depends(current_user),db=Depends(get_db)):
    batch=own_batch(db,user,batch_id)
    return {'id':batch.id,'status':batch.status,'rows':batch.rows,'result':batch.result}

@router.post('/{batch_id}/confirm')
def confirm(batch_id:str,data:ConfirmIn,user=Depends(current_user),db=Depends(get_db)):
    writer(user)
    batch=own_batch(db,user,batch_id)
    if batch.status=='confirmed':
        return batch.result
    claim=db.execute(update(ImportBatch).where(ImportBatch.id==batch_id,ImportBatch.status=='preview').values(status='processing'),execution_options={'synchronize_session':False})
    if claim.rowcount!=1:
        raise HTTPException(409,'该批次正在处理中，请刷新')
    result={'inserted':0,'duplicates':0,'failed':0,'rows':[],'customer_ids':[]}
    for i,row in enumerate(data.rows,1):
        row=dict(row,row=row.get('row',i))
        checked,customer,message_data=validate_row(db,user,row)
        if checked['error']:
            result['failed']+=1
            checked['status']='failed'
        else:
            message=insert_message(db,customer,user,message_data,batch_id)
            checked['status']='inserted' if message else 'duplicate'
            result['inserted' if message else 'duplicates']+=1
            result['customer_ids'].append(customer.id)
        result['rows'].append(checked)
    result['customer_ids']=sorted(set(result['customer_ids']))
    batch.status='confirmed'
    batch.rows=result['rows']
    batch.result=result
    audit(db,user,'import.confirm',batch_id,{k:result[k] for k in ['inserted','duplicates','failed']})
    db.commit()
    return result

@router.get('/{batch_id}/errors')
def errors(batch_id:str,user=Depends(current_user),db=Depends(get_db)):
    batch=own_batch(db,user,batch_id)
    stream=StringIO()
    out=csv.writer(stream)
    out.writerow(['行号','客户ID','时间','说话人','内容','错误'])
    for row in batch.rows:
        if row.get('error'):
            values=[row.get(k,'') for k in ['row','customer_id','sent_at','speaker','content','error']]
            out.writerow(["'"+str(v) if str(v).startswith(('=','+','-','@','\t','\r')) else v for v in values])
    audit(db,user,'import.errors_export',batch.id)
    db.commit()
    return Response(('\ufeff'+stream.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=import-errors.csv'})
