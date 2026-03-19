#!/usr/bin/env python3
"""
Seed script: creates demo users, workspaces, and roles.

Usage (from backend/ directory):
    python scripts/seed_db.py

Creates:
    admin@ragops.dev  / Admin1234   (role: admin)
    user@ragops.dev   / User1234    (role: user)
    Each user gets a default workspace.
"""
import asyncio
import sys
import os

# Add backend root to path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, ensure_pgvector_extension
from app.core.security import hash_password
from app.models.user import User, Workspace
from app.models import *   # ensure all models are registered


SEED_USERS = [
    {
        "email": "admin@ragops.dev",
        "full_name": "Admin User",
        "password": "Admin1234",
        "role": "admin",
        "workspace_name": "Admin Workspace",
        "workspace_desc": "Default admin workspace for testing.",
    },
    {
        "email": "user@ragops.dev",
        "full_name": "Demo User",
        "password": "User1234",
        "role": "user",
        "workspace_name": "Demo Workspace",
        "workspace_desc": "Default user workspace for demo queries.",
    },
]


async def seed():
    print("🌱 Starting database seed...")

    await ensure_pgvector_extension()

    async with AsyncSessionLocal() as db:
        for seed_data in SEED_USERS:
            # Skip if user already exists (idempotent)
            existing = await db.execute(
                select(User).where(User.email == seed_data["email"])
            )
            if existing.scalar_one_or_none():
                print(f"  ⏭  User {seed_data['email']} already exists, skipping.")
                continue

            user = User(
                email=seed_data["email"],
                full_name=seed_data["full_name"],
                hashed_password=hash_password(seed_data["password"]),
                role=seed_data["role"],
                is_active=True,
            )
            db.add(user)
            await db.flush()

            workspace = Workspace(
                owner_id=user.id,
                name=seed_data["workspace_name"],
                description=seed_data["workspace_desc"],
            )
            db.add(workspace)
            await db.flush()

            print(f"  ✅ Created user: {seed_data['email']} (role={seed_data['role']})")
            print(f"     Workspace:  {seed_data['workspace_name']} (id={workspace.id})")
            print(f"     Password:   {seed_data['password']}")

        await db.commit()

    print("\n✅ Seed complete.")
    print("\nDemo credentials:")
    print("  Admin : admin@ragops.dev / Admin1234")
    print("  User  : user@ragops.dev  / User1234")


if __name__ == "__main__":
    asyncio.run(seed())
