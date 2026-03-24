import asyncio
import sys
import uuid

from app.api.documents import _run_ingestion

async def test():
    await _run_ingestion(
        document_id=uuid.UUID("c9176650-b0cd-4953-8840-5327ec8bc494"),
        file_bytes=b"dummy content",
        mime_type="text/plain",
        user_id=uuid.UUID("c9176650-b0cd-4953-8840-5327ec8bc494") # Just placeholder
    )
    print("Test finished")

if __name__ == "__main__":
    asyncio.run(test())
