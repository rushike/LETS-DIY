import os
import json
import time
import random
import asyncio
from pathlib import Path
from typing import Optional
import uvicorn
from fastapi import FastAPI, Request, Body
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Query


from pydantic import BaseModel

from telethon.tl.types import Channel, Chat, DocumentAttributeFilename, DocumentAttributeVideo
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest

# SQLAlchemy Imports
from sqlalchemy import Column, String, Text, Integer, Boolean, delete, create_engine, func, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.future import select

from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, BigInteger, ForeignKey
from sqlalchemy.orm import declarative_base
from sqlalchemy import LargeBinary
import datetime

# --- Database Setup ---
DATABASE_URL = "sqlite+aiosqlite:///cache.db"
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    is_bot = Column(Boolean, default=False)
    phone = Column(String, nullable=True)     # For regular users
    bot_token = Column(String, nullable=True) # For bots
    api_id = Column(String, nullable=False)
    api_hash = Column(String, nullable=False)

    def __repr__(self):
        return f"<User(id={self.id}, is_bot={self.is_bot}, phone='{self.phone}', bot_token='{self.bot_token}')>"

class ChannelCache(Base):
    __tablename__ = "channel_cache"
    phone = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    data = Column(Text)
    timestamp = Column(Integer)

    def __repr__(self):
        return f"<ChannelCache(phone='{self.phone}', user_id={self.user_id}, timestamp={self.timestamp})>"

class FileTree(Base):
    __tablename__ = "file_tree"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    parent_dir = Column(String)
    file_path = Column(String)
    status = Column(String, default="pending")
    size = Column(Integer)
    channel_id = Column(BigInteger, nullable=False)
    file_sync = Column(Boolean, default=False)

    def __repr__(self):
        filename = os.path.basename(self.file_path) if self.file_path else "None"
        return f"<FileTree(id={self.id}, user_id={self.user_id}, file='{filename}', status='{self.status}', sync={self.file_sync})>"


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"
    message_id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    channel_id = Column(BigInteger, index=True)
    text = Column(Text, nullable=True)
    date = Column(DateTime)
    
    has_media = Column(Boolean, default=False)
    media_type = Column(String, nullable=True) 
    
    document_id = Column(BigInteger, nullable=True)
    access_hash = Column(BigInteger, nullable=True)
    file_name = Column(String, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    mime_type = Column(String, nullable=True)
    
    file_reference = Column(LargeBinary, nullable=True)
    
    duration = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    thumbnail = Column(LargeBinary, nullable=True)
    thumbnail_type = Column(String, nullable=True)
    last_synced_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        content = (self.text[:20] + '...') if self.text and len(self.text) > 20 else self.text
        media_info = f" | {self.media_type}: {self.file_name}" if self.has_media else ""
        return f"<TelegramMessage(id={self.message_id}, channel={self.channel_id}, text='{content}'{media_info})>"
    
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

app = FastAPI(title="Telegram Forwarder API")

# --- Models ---
class TelegramConfig(BaseModel):
    api_id: str
    api_hash: str
    phone: Optional[str] = ""
    bot_token: Optional[str] = ""
    is_bot: bool = False
    channels: Optional[str] = ""

class TokenVerify(BaseModel):
    phone: str
    code: str
    api_id: str
    api_hash: str



# --- Global State ---
# We store the client in a way that survives requests
tg_client: TelegramClient = None


from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

import datetime
from telethon.tl.types import (
    MessageMediaDocument, MessageMediaPhoto, 
    PhotoStrippedSize, DocumentAttributeFilename, 
    DocumentAttributeVideo
)

def reconstruct_stripped_thumb(stripped_bytes: bytes) -> bytes:
    """Prepends the missing JPEG header to PhotoStrippedSize bytes."""
    header = b'\xff\xd8\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xdb\x00C\x01\t\t\t\x0c\x0b\x0c\x18\r\r\x182!\x1c!22222222222222222222222222222222222222222222222222\xff\xc0\x00\x11\x08\x00\x00\x00\x00\x03\x01"\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07aq\x13"2\x81\x08\x14B\x91\xa1\xb1\xc1\x09#3R\xf0\x15$4br\xd1\x16\x17\x18\x19\x1a%&\'()*56789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x82\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00'
    return header[:164] + stripped_bytes[1:2] + header[165:166] + stripped_bytes[2:3] + header[167:] + stripped_bytes[3:]

async def get_user_id_by_identifier(session: AsyncSession, identifier: str) -> Optional[int]:
    result = await session.execute(
        select(User.id).where((User.phone == identifier) | (User.bot_token == identifier))
    )
    return result.scalar()

async def sync_messages_to_db(session: AsyncSession, messages: list, channel_id: int, user_id: int):
    for msg in messages:
        doc_details = {}

        # --- Handle Documents (Videos, Files, etc.) ---
        if msg.media and isinstance(msg.media, MessageMediaDocument):
            doc = msg.media.document
            doc_details = {
                "media_type": "Document",
                "document_id": doc.id,
                "access_hash": doc.access_hash,
                "file_size": doc.size,
                "mime_type": doc.mime_type,
                "file_reference": doc.file_reference,
            }
            if doc.thumbs:
                thumb = doc.thumbs[0]
                doc_details["thumbnail_type"] = getattr(thumb, 'type', 'unknown')
                # If it's a stripped thumb, fix it before saving
                raw_bytes = getattr(thumb, 'bytes', None)
                if isinstance(thumb, PhotoStrippedSize) and raw_bytes:
                    doc_details["thumbnail"] = reconstruct_stripped_thumb(raw_bytes)
                else:
                    doc_details["thumbnail"] = raw_bytes

            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeFilename):
                    doc_details["file_name"] = attr.file_name
                elif isinstance(attr, DocumentAttributeVideo):
                    doc_details["duration"] = int(attr.duration)
                    doc_details["width"] = attr.w
                    doc_details["height"] = attr.h

        # --- Handle Photos (New Logic) ---
        elif msg.media and isinstance(msg.media, MessageMediaPhoto):
            photo = msg.media.photo
            doc_details = {
                "media_type": "Photo",
                "document_id": photo.id,
                "access_hash": photo.access_hash,
                "file_reference": photo.file_reference,
                "mime_type": "image/jpeg"
            }
            # Photos have sizes[] instead of thumbs[]
            if photo.sizes:
                # Typically index 0 is the smallest thumbnail
                thumb = photo.sizes[0]
                doc_details["thumbnail_type"] = getattr(thumb, 'type', 'unknown')
                
                raw_bytes = getattr(thumb, 'bytes', None)
                if isinstance(thumb, PhotoStrippedSize) and raw_bytes:
                    doc_details["thumbnail"] = reconstruct_stripped_thumb(raw_bytes)
                else:
                    doc_details["thumbnail"] = raw_bytes

        # --- Merge into DB ---
        db_msg = TelegramMessage(
            message_id=msg.id,
            channel_id=channel_id,
            user_id=user_id,
            text=msg.text or "",
            date=msg.date.replace(tzinfo=None) if msg.date else None,
            has_media=msg.media is not None,
            **doc_details,
            last_synced_at=datetime.datetime.utcnow()
        )
        await session.merge(db_msg)
    
    await session.commit()

async def get_client(api_id: str, api_hash: str, phone: Optional[str]) -> TelegramClient:
    global tg_client
    session_path = f"{phone}"
    
    if tg_client is not None and tg_client.session.filename != f"{session_path}.session":
        await tg_client.disconnect()
        tg_client = None

    if tg_client is None:
        tg_client = TelegramClient(session_path, api_id, api_hash)
    
    if not tg_client.is_connected():
        await tg_client.connect()
        
    return tg_client

import base64

def message_to_dict(msg: TelegramMessage):
    """Converts model to dict and encodes binary data to Base64 strings."""
    # Convert SQLAlchemy object to a standard dictionary
    data = {c.name: getattr(msg, c.name) for c in msg.__table__.columns}
    
    # Encode 'thumbnail' if it exists
    if data.get("thumbnail"):
        data["thumbnail"] = base64.b64encode(data["thumbnail"]).decode('utf-8')
        
    # Encode 'file_reference' if it exists
    if data.get("file_reference"):
        data["file_reference"] = base64.b64encode(data["file_reference"]).decode('utf-8')
    
    # DateTime objects also need to be strings for JSON
    if data.get("date"):
        data["date"] = data["date"].isoformat()
    if data.get("last_synced_at"):
        data["last_synced_at"] = data["last_synced_at"].isoformat()

    return data


def telethon_msg_to_dict(msg):
    """Converts a raw Telethon message to a dict compatible with message_to_dict."""
    # Logic similar to your sync_messages_to_db but returns a dict
    # This ensures your UI receives consistent data
    return {
        "message_id": msg.id,
        "text": msg.text or "",
        "date": msg.date.isoformat() if msg.date else None,
        "has_media": msg.media is not None,
        "file_name": getattr(msg.file, 'name', None) if msg.file else None,
        "file_size": msg.file.size if msg.file else None,
        # Add other fields you need for the UI here
    }

async def get_cached_entity(channel_id: int):
    """
    Retrieves entity safely. 
    1. Checks Telethon's internal session first.
    2. Uses ID directly (Telethon resolves automatically if seen before).
    3. Falls back to get_entity only if necessary.
    """
    if tg_client is None:
        return None
        
    try:
        # Most Telethon methods work fine with just the ID integer 
        # if the session has seen the channel once.
        return await tg_client.get_input_entity(channel_id)
    except (ValueError, TypeError):
        # Fallback to full fetch if it's a new/unknown ID
        print(f"Cache miss for {channel_id}, fetching from Telegram...")
        return await tg_client.get_entity(channel_id)

# Global Queue for background syncing, sync to local db
sync_queue = asyncio.Queue()
processing_channels = set() # To prevent adding the same channel multiple times

async def background_sync_worker():
    while True:
        task = await sync_queue.get()
        channel_id = task.get("channel_id")
        phone = task.get("phone")
        if channel_id in processing_channels:
            sync_queue.task_done()
            continue
            
        processing_channels.add(channel_id)
        
        try:
            async with async_session() as session:
                user_id = await get_user_id_by_identifier(session, phone)
                user_result = await session.execute(select(User).where(User.id == user_id))
                user = user_result.scalars().first()
                if not user:
                    print(f"User not found for identifier {phone}")
                    continue
                    
                identifier = user.phone or user.bot_token
                await get_client(user.api_id, user.api_hash, identifier)
                
                # 1. Get the most recent message date from the DB
                result = await session.execute(
                    select(TelegramMessage.date)
                    .where(TelegramMessage.channel_id == channel_id, TelegramMessage.user_id == user_id)
                    .order_by(TelegramMessage.date.desc())
                    .limit(1)
                )
                last_sync_ts = result.scalar()
                
                entity = await tg_client.get_entity(channel_id)
                batch = []
                new_messages_found = 0
                
                # 2. Iterate messages (newest first)
                async for msg in tg_client.iter_messages(entity):
                    # Convert Telegram's aware datetime to naive for comparison
                    msg_date = msg.date.replace(tzinfo=None)
                    
                    # If we've reached messages we already have, stop fetching
                    if last_sync_ts and msg_date <= last_sync_ts:
                        break
                    
                    batch.append(msg)
                    new_messages_found += 1
                    
                    # Process in batches of 100
                    if len(batch) >= 100:
                        await sync_messages_to_db(session, batch, channel_id, user_id)
                        batch = []
                        await asyncio.sleep(1) # Rate-limit friendly
                
                # final batch
                if batch:
                    await sync_messages_to_db(session, batch, channel_id, user_id)
                
                print(f"Sync complete for {channel_id}. Found {new_messages_found} new messages.")

        except Exception as e:
            print(f"Sync Error: {e}")
        finally:
            processing_channels.remove(channel_id)
            sync_queue.task_done()

# upload to telegram channel
# Semaphore to limit simultaneous uploads (Safe range: 1-3)
upload_semaphore = asyncio.Semaphore(1)
async def background_upload_worker():
    """
    Polls the FileTree table and uploads files with a staggered parallel start.
    """
    while True:
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(FileTree).where(FileTree.status == "pending").order_by(func.random()).limit(1)
                )
                task = result.scalars().first()
                if not task:
                    await asyncio.sleep(5)
                    continue

                user_result = await session.execute(select(User).where(User.id == task.user_id))
                user = user_result.scalars().first()
                if not user:
                    await asyncio.sleep(5)
                    continue
                    
                identifier = user.phone or user.bot_token
                client = await get_client(user.api_id, user.api_hash, identifier)
                if not client or not client.is_connected():
                    await asyncio.sleep(5)
                    continue

                stagger_delay = random.uniform(1, 5)
                print(f"Staggering upload for {stagger_delay:.2f}s: {task.file_path}")
                    
                await asyncio.sleep(stagger_delay);
                # 1. Acquire the semaphore slot
                async with upload_semaphore:
                    # 2. Stagger the start: Wait 5-30 seconds before beginning the upload
                    # This prevents multiple uploads from hitting the server at the exact same second
                    # stagger_delay = random.uniform(5, 15)
                    # print(f"Staggering upload for {stagger_delay:.2f}s: {task.file_path}")
                    # await asyncio.sleep(stagger_delay)

                    # 3. Mark as processing after the delay
                    task.status = "uploading..."
                    await session.commit()

                    print(f"Starting upload: {task.file_path}")
                    
                    entity = await get_cached_entity(task.channel_id)
                    
                    msg = await tg_client.send_file(
                        entity, 
                        task.file_path, 
                        video=True, 
                        supports_streaming=True,
                        caption=os.path.basename(task.file_path)
                    )

                    # 4. Success: Update DB
                    task.status = "uploaded"
                    task.file_sync = True
                    # Re-bind task if session expired, or use specialized session for sync
                    await sync_messages_to_db(session, [msg], task.channel_id, task.user_id)
                    await session.commit()
                    print(f"Finished upload: {task.file_path}")

        except Exception as e:
            print(f"Upload Error: {e}")
            try:
                async with async_session() as session:
                    await session.execute(
                        update(FileTree)
                        .where(FileTree.id == task.id)
                        .values(status=f"error: {str(e)[:100]}")
                    )
                    await session.commit()
            except: pass
        
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    asyncio.create_task(background_sync_worker())
    asyncio.create_task(background_upload_worker())

    # 3. RESET STUCK UPLOADS
    # This finds any rows that were "uploading..." when the app closed
    # and moves them back to "pending" so the worker can try again.
    async with async_session() as session:
        await session.execute(
            update(FileTree)
            .where(FileTree.status == "uploading...")
            .values(status="pending")
        )
        await session.commit()
        print("Database Maintenance: Reset 'uploading' tasks to 'pending'.")


from sqlalchemy import delete

@app.post("/api/file-load")
async def load_files(
    parent_dir: str = Query(...), 
    file_type: str = Query("mp4"),
    channel_id: int = Query(...), # Changed to int for consistency with DB
    phone: str = Query(...)
):
    path = Path(parent_dir)
    if not path.exists() or not path.is_dir():
        return {"status": "error", "message": "Invalid directory path."}

    try:
        async with async_session() as session:
            # 1. Clear existing records for this parent_dir
            await session.execute(
                delete(FileTree).where(FileTree.parent_dir == parent_dir)
            )
            
            # 2. Get a list of all filenames already synced in Telegram for this channel for this user
            user_id = await get_user_id_by_identifier(session, phone)
            if not user_id:
                return {"status": "error", "message": "User not registered. Please complete setup."}
            
            synced_result = await session.execute(
                select(TelegramMessage.file_name)
                .where(TelegramMessage.channel_id == channel_id, TelegramMessage.user_id == user_id)
                .where(TelegramMessage.file_name.isnot(None))
            )
            synced_filenames = set(synced_result.scalars().all())
            
            # 3. Walk the directory
            new_entries = []
            
            # Support comma-separated file types
            valid_exts = tuple(f".{ext.strip().lstrip('.')}".lower() for ext in file_type.split(",") if ext.strip())
            
            for root, _, files in os.walk(parent_dir):
                for file in files:
                    if not valid_exts or file.lower().endswith(valid_exts):
                        full_path = os.path.join(root, file)
                        file_size = os.path.getsize(full_path)
                        
                        # Set file_sync to True if the filename exists in our Telegram cache
                        is_synced = file in synced_filenames
                        
                        new_entries.append(
                            FileTree(
                                parent_dir=parent_dir,
                                file_path=full_path,
                                size=file_size,
                                status="uploaded" if is_synced else "pending",
                                channel_id=channel_id,
                                user_id=user_id,
                                file_sync=is_synced 
                            )
                        )
            
            # 4. Bulk insert
            if new_entries:
                session.add_all(new_entries)
            
            await session.commit()
            
        return {
            "status": "success", 
            "files_found": len(new_entries),
            "synced_count": len([f for f in new_entries if f.file_sync]),
            "message": f"Scanned {parent_dir}. Synced files marked based on Channel {channel_id}."
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/file-tree/refresh-status")
async def refresh_file_status(
    parent_dir: str = Query(...),
    channel_id: int = Query(...),
    phone: str = Query(...)
):
    """
    Cross-references the file_tree with telegram_messages to update 
    sync status based on matching filenames for a specific channel.
    """
    try:
        async with async_session() as session:
            user_id = await get_user_id_by_identifier(session, phone)
            if not user_id:
                return {"status": "error", "message": "User not registered. Please complete setup."}
            # 1. Fetch all unique filenames already synced in this channel
            synced_result = await session.execute(
                select(TelegramMessage.file_name)
                .where(TelegramMessage.channel_id == channel_id, TelegramMessage.user_id == user_id)
                .where(TelegramMessage.file_name.isnot(None))
            )
            synced_filenames = set(synced_result.scalars().all())

            # 2. Fetch all local files currently tracked for this parent directory
            local_files_result = await session.execute(
                select(FileTree).where(FileTree.parent_dir == parent_dir, FileTree.user_id == user_id)
            )
            local_files = local_files_result.scalars().all()

            updated_count = 0
            for file_entry in local_files:
                # Extract the filename from the full path
                filename = os.path.basename(file_entry.file_path)
                
                # Check if it exists in the Telegram synced set
                is_now_synced = filename in synced_filenames
                
                # Only update if the status has actually changed
                if file_entry.file_sync != is_now_synced:
                    file_entry.file_sync = is_now_synced
                    file_entry.status = "uploaded" if is_now_synced else "pending"
                    updated_count += 1

            if updated_count > 0:
                await session.commit()

            return {
                "status": "success",
                "message": f"Refreshed status for {len(local_files)} files.",
                "updated_records": updated_count,
                "currently_synced": len([f for f in local_files if f.file_sync])
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/file-tree")
async def get_file_tree(
    channel_id: int = Query(...),
    phone: str = Query(...)
):
    """
    Returns the entire contents of the file_tree table.
    """
    async with async_session() as session:
        user_id = await get_user_id_by_identifier(session, phone)
        if not user_id:
            return {"status": "error", "message": "User not registered.", "count": 0, "data": []}
        result = await session.execute(select(FileTree).filter(FileTree.channel_id == channel_id, FileTree.user_id == user_id))
        rows = result.scalars().all()
        
        # Convert SQLAlchemy objects to dictionaries for JSON response
        tree_data = [
            {
                "id": r.id,
                "parent_dir": r.parent_dir,
                "file_path": r.file_path,
                "status": r.status,
                "size": r.size,
                "channel_id": r.channel_id,
                "file_sync": r.file_sync
            }
            for r in rows
        ]
        return {"status": "success", "count": len(tree_data), "data": tree_data}


@app.delete("/api/file-delete")
async def delete_file_group(parent_dir: str = Query(...), phone: str = Query(...)):
    """
    Deletes all file records associated with a specific parent directory.
    """
    try:
        async with async_session() as session:
            user_id = await get_user_id_by_identifier(session, phone)
            if not user_id:
                return {"status": "error", "message": "User not registered."}
            result = await session.execute(
                delete(FileTree).where(FileTree.parent_dir == parent_dir, FileTree.user_id == user_id)
            )
            await session.commit()
            
            return {
                "status": "success", 
                "message": f"Removed records for {parent_dir}",
                "rows_deleted": result.rowcount
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/channels")
async def list_channels(
    config: TelegramConfig, 
    own: bool = Query(False), 
    refresh: bool = Query(False)
):
    """
    Retrieves channels. Checks SQLite cache first unless refresh=True.
    """
    # 1. Check Cache First
    if not refresh:
        async with async_session() as session:
            result = await session.execute(
                select(ChannelCache).where(ChannelCache.phone == config.phone)
            )
            cache_entry = result.scalars().first()
            if cache_entry:
                # Return cached data
                channels = json.loads(cache_entry.data)
                # Filter 'own' on the fly from cache if needed
                if own:
                    channels = [c for c in channels if c.get('is_owner')]
                return {"status": "success", "source": "cache", "channels": channels}

    # 2. Fetch from Telegram if refresh=True or Cache Miss
    client = await get_client(config.api_id, config.api_hash, config.phone)
    if not await client.is_user_authorized():
        return {"status": "error", "message": "User not authorized."}

    try:
        channels_list = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, (Channel, Chat)):
                is_owner = getattr(entity, 'creator', False)
                channels_list.append({
                    "id": dialog.id,
                    "title": dialog.name,
                    "username": getattr(entity, 'username', None),
                    "is_owner": is_owner,
                    "is_channel": dialog.is_channel
                })
        
        # 3. Save/Update Cache
        async with async_session() as session:
            user_id = await get_user_id_by_identifier(session, config.phone)
            if user_id:
                new_cache = ChannelCache(
                    phone=config.phone,
                    user_id=user_id,
                    data=json.dumps(channels_list),
                    timestamp=int(time.time())
                )
                await session.merge(new_cache) # merge updates if exists, else inserts
                await session.commit()

        # Final filter for the response
        final_list = [c for c in channels_list if c.get('is_owner')] if own else channels_list
        return {"status": "success", "source": "telegram", "channels": final_list}

    except Exception as e:
        return {"status": "error", "message": str(e)}

from telethon.tl.types import Message
from telethon.utils import get_display_name

@app.get("/api/channel/messages")
async def get_channel_messages(
    channel_id: int = Query(...),
    phone: str = Query(...),
    limit: int = Query(100000)
):
    global tg_client
    
    # 1. Push to queue for the background worker to handle DB storage
    await sync_queue.put({"channel_id": channel_id, "phone": phone})

    async with async_session() as session:
        user_id = await get_user_id_by_identifier(session, phone)
        if not user_id:
            return {"status": "error", "message": "User not registered."}
        # 2. Try to get messages from local DB
        result = await session.execute(
            select(TelegramMessage)
            .where(TelegramMessage.channel_id == channel_id, TelegramMessage.user_id == user_id)
            .order_by(TelegramMessage.message_id.desc())
            .limit(limit)
        )
        rows = result.scalars().all()

        # 3. IF DB HAS DATA: Return it
        if rows:
            return {
                "status": "success",
                "source": "database",
                "messages": [message_to_dict(r) for r in rows]
            }

        # 4. IF DB IS EMPTY: Fetch from Client and return IMMEDIATELY
        # We do NOT save to DB here; we let the background task handle that later.
        if tg_client is None or not tg_client.is_connected():
            return {"status": "error", "message": "Client not connected"}
        
        try:
            entity = await tg_client.get_entity(channel_id)
            messages_to_return = []
            
            async for msg in tg_client.iter_messages(entity, limit=limit):
                # Convert raw Telethon object to dict for the JSON response
                messages_to_return.append(telethon_msg_to_dict(msg))
            
            return {
                "status": "success",
                "source": "telegram_direct",
                "sync_status": "background_sync_queued",
                "count": len(messages_to_return),
                "messages": messages_to_return
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Direct fetch failed: {str(e)}"}
@app.get("/api/channel/{channel_id}")
async def get_channel_detail(channel_id: int, phone: str = Query(...)):
    """
    Fetches details for a specific channel. 
    Checks cache first; if missing, fetches from Telegram and updates cache.
    """
    # 1. Try to find in Cache
    async with async_session() as session:
        result = await session.execute(
            select(ChannelCache).where(ChannelCache.phone == phone)
        )
        cache_entry = result.scalars().first()
        
        if cache_entry:
            channels = json.loads(cache_entry.data)
            channel = next((c for c in channels if str(c['id']) == str(channel_id)), None)
            if channel:
                return {"status": "success", "source": "cache", "channel": channel}

    # 2. Cache Miss or Channel Not Found: Fetch from Telegram
    # We need the API credentials. For this logic to work, 
    # the client must already be initialized/authenticated.
    if tg_client is None or not await tg_client.is_user_authorized():
        return {"status": "error", "message": "Client not authorized. Please log in first."}

    try:
        channels_list = []
        target_channel = None

        async for dialog in tg_client.iter_dialogs():
            entity = dialog.entity
            if isinstance(entity, (Channel, Chat)):
                is_owner = getattr(entity, 'creator', False)
                channel_data = {
                    "id": dialog.id,
                    "title": dialog.name,
                    "username": getattr(entity, 'username', None),
                    "is_owner": is_owner,
                    "is_channel": dialog.is_channel
                }
                channels_list.append(channel_data)
                
                # Check if this is the one we are looking for
                if str(dialog.id) == str(channel_id):
                    target_channel = channel_data

        # 3. Update the Cache with the new list
        async with async_session() as session:
            user_id = await get_user_id_by_identifier(session, phone)
            if user_id:
                new_cache = ChannelCache(
                    phone=phone,
                    user_id=user_id,
                    data=json.dumps(channels_list),
                    timestamp=int(time.time())
                )
                await session.merge(new_cache)
                await session.commit()

        if target_channel:
            return {"status": "success", "source": "telegram", "channel": target_channel}
        
        return {"status": "error", "message": "Channel not found on Telegram account."}

    except Exception as e:
        return {"status": "error", "message": str(e)}
    

@app.post("/api/init")
async def initialize_session(config: TelegramConfig):
    """
    Attempts to connect to an existing session without sending a new login code.
    Returns whether the user is already authorized or needs to log in.
    """
    try:
        # get_client handles the .connect() call internally
        client = await get_client(config.api_id, config.api_hash, config.phone)
        
        is_authorized = await client.is_user_authorized()
        
        if is_authorized:
            return {
                "status": "authorized", 
                "message": "Session restored successfully."
            }
        else:
            return {
                "status": "unauthorized", 
                "message": "No active session found. Please proceed to setup/send code."
            }
    except Exception as e:
        return {"status": "error", "message": f"Initialization failed: {str(e)}"}


@app.post("/api/setup")
async def setup_account(config: TelegramConfig):
    # Save the config to the 'users' table
    async with async_session() as session:
        # Check if user already exists
        identifier_field = User.bot_token if config.is_bot else User.phone
        identifier_value = config.bot_token if config.is_bot else config.phone
        
        result = await session.execute(
            select(User).where(identifier_field == identifier_value)
        )
        existing_user = result.scalars().first()
        
        if existing_user:
            existing_user.api_id = config.api_id
            existing_user.api_hash = config.api_hash
        else:
            new_user = User(
                api_id=config.api_id,
                api_hash=config.api_hash,
                is_bot=config.is_bot,
                phone=config.phone,
                bot_token=config.bot_token
            )
            session.add(new_user)
        await session.commit()

    identifier = config.bot_token if config.is_bot else config.phone
    
    # Telethon requires a valid string for session name
    session_name = identifier.split(":")[0] if config.is_bot and identifier else identifier
    if not session_name:
        return {"status": "error", "message": "Phone or bot token is required."}

    client = await get_client(config.api_id, config.api_hash, session_name)
    
    # Check if we are already logged in BEFORE asking for a code
    if await client.is_user_authorized():
        return {"status": "authorized", "message": "You are already logged in!"}
    
    try:
        if config.is_bot:
            await client.start(bot_token=config.bot_token)
            return {"status": "authorized", "message": "Bot successfully authenticated!"}
        else:
            # Only request code if NOT authorized
            await client.send_code_request(config.phone)
            return {"status": "code_sent", "message": "Please check your Telegram for the login code."}
    except Exception as e:
        # This will catch the SendCodeUnavailableError and explain it to the UI
        return {"status": "error", "message": f"Telegram error: {str(e)}"}

@app.post("/api/settings/user")
async def save_user_settings(config: TelegramConfig):
    """
    Saves user configuration to the database without attempting to
    trigger the Telegram authentication flow.
    """
    try:
        async with async_session() as session:
            identifier_field = User.bot_token if config.is_bot else User.phone
            identifier_value = config.bot_token if config.is_bot else config.phone
            
            if not identifier_value:
                return {"status": "error", "message": "Phone or bot token is required."}

            result = await session.execute(
                select(User).where(identifier_field == identifier_value)
            )
            existing_user = result.scalars().first()
            
            if existing_user:
                existing_user.api_id = config.api_id
                existing_user.api_hash = config.api_hash
                if config.is_bot:
                    existing_user.bot_token = config.bot_token
                else:
                    existing_user.phone = config.phone
            else:
                new_user = User(
                    api_id=config.api_id,
                    api_hash=config.api_hash,
                    is_bot=config.is_bot,
                    phone=config.phone,
                    bot_token=config.bot_token
                )
                session.add(new_user)
            await session.commit()
            return {"status": "success", "message": "User settings stored successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/verify")
async def verify_code(data: TokenVerify):
    global tg_client
    # Ensure client is connected
    client = await get_client(data.api_id, data.api_hash, data.phone)
    
    try:
        # Sign in using the code received from the UI
        await client.sign_in(data.phone, data.code)
        return {"status": "success", "message": "Successfully authenticated!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

BASE_DIR = Path(__file__).resolve().parent
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "public"), html=True), name="public")


if __name__ == "__main__":
    # FastAPI uses uvicorn instead of app.run()
    uvicorn.run(app, host="0.0.0.0", port=9000)
