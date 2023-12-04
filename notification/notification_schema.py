from pydantic import BaseModel

class Sub_List(BaseModel):
    class_id: int
    email: str
    webhook_url: str