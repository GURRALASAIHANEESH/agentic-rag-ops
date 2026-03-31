import asyncio
from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.document import Document
from app.workers.ingestion_worker import run_ingestion_task

async def requeue_pending_documents():
    print("🔍 Scanning database for stuck 'pending' documents...")
    
    async with async_session_maker() as session:
        # Find all documents where status is 'pending'
        query = select(Document.id, Document.filename).where(Document.status == "pending")
        result = await session.execute(query)
        pending_docs = result.all()
        
        if not pending_docs:
            print("✅ No pending documents found. Everything is up to date!")
            return

        print(f"⚠️ Found {len(pending_docs)} pending documents. Re-queuing to Celery...")
        
        for doc in pending_docs:
            doc_id_str = str(doc.id)
            run_ingestion_task.delay(doc_id_str)
            print(f"  -> Queued: {doc.filename} ({doc_id_str})")
            
        print("🚀 All tasks successfully sent to the worker queue!")

if __name__ == "__main__":
    asyncio.run(requeue_pending_documents())
