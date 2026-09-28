"""
启动uvicorn
"""
import uvicorn
from customer_service.config.config import settings

if __name__ == '__main__':
    uvicorn.run(app="customer_service.api.app:app", host=settings.app_host, port=settings.app_port)
