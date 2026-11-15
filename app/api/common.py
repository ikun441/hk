from datetime import datetime
from sqlalchemy import select, func

def serialize(row, fields):
    result={}
    for name in fields.split():
        value=getattr(row,name)
        result[name]=value.isoformat()+'Z' if isinstance(value,datetime) else value
    return result

def page_query(db, statement, page=1, page_size=20):
    total=db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    return {'total':total,'page':page,'page_size':page_size,'items':list(db.scalars(statement.offset((page-1)*page_size).limit(page_size)))}

CUSTOMER_FIELDS='id name industry contact contact_info source owner_id department_id status last_followup_at notes archived created_at updated_at'
MESSAGE_FIELDS='id customer_id batch_id speaker sent_at content source created_by created_at'
REQUEST_FIELDS='id customer_id submitted_by base_version proposal original_proposal source status reviewed_by reviewed_at review_note applied_delta created_at updated_at'
