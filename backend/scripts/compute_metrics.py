#!/usr/bin/env python3
"""
Computes 3 demo metrics on recorded queries:

  1. Citation Precision@K  — of top-K retrieved chunks, how many were
                             actually cited in the answer?
  2. Average Response Latency — mean latency_ms across all query logs
  3. Critic Precision       — fraction of claims marked 'verified'
                              out of total claims across all queries

Usage (from backend/ directory):
    python scripts/compute_metrics.py

Output: prints a metrics report + writes metrics_report.json
"""
import asyncio
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func
from app.core.database import AsyncSessionLocal
from app.models.audit import QueryLog, Citation, AuditLog
from app.models import *


async def compute():
    print("📊 Computing RAG quality metrics...\n")

    async with AsyncSessionLocal() as db:
        # ── 1. Average Response Latency ───────────────────────────────────
        lat_result = await db.execute(
            select(func.avg(QueryLog.latency_ms), func.count(QueryLog.id))
            .where(QueryLog.latency_ms.isnot(None))
        )
        avg_latency, total_queries = lat_result.one()

        # ── 2. Citation Precision@K ───────────────────────────────────────
        # For each query: citations_used / total_chunks_retrieved
        # We proxy this as: citations saved / top_k (default 5)
        TOP_K = 5
        cite_result = await db.execute(
            select(
                QueryLog.id,
                func.count(Citation.id).label("citations_used")
            )
            .join(Citation, Citation.query_log_id == QueryLog.id, isouter=True)
            .group_by(QueryLog.id)
        )
        rows = cite_result.fetchall()
        if rows:
            precision_scores = [
                min(row.citations_used / TOP_K, 1.0) for row in rows
            ]
            avg_precision = sum(precision_scores) / len(precision_scores)
        else:
            avg_precision = 0.0

        # ── 3. Critic Precision ───────────────────────────────────────────
        # From audit_logs where event_type='critic_result'
        critic_result = await db.execute(
            select(AuditLog.payload)
            .where(AuditLog.event_type == "critic_result")
        )
        critic_rows = critic_result.scalars().all()

        if critic_rows:
            total_verified = sum(r.get("verified", 0) for r in critic_rows)
            total_claims = sum(
                r.get("verified", 0) + r.get("unverified", 0) + r.get("partial", 0)
                for r in critic_rows
            )
            critic_precision = total_verified / total_claims if total_claims > 0 else 0.0
            avg_critic_score = sum(
                r.get("overall_score", 0) for r in critic_rows
            ) / len(critic_rows)
        else:
            critic_precision = 0.0
            avg_critic_score = 0.0

    # ── Report ────────────────────────────────────────────────────────────
    report = {
        "total_queries": int(total_queries or 0),
        "avg_latency_ms": round(float(avg_latency or 0), 2),
        "citation_precision_at_k": round(avg_precision, 4),
        "critic_precision": round(critic_precision, 4),
        "avg_critic_score": round(avg_critic_score, 4),
    }

    print("=" * 50)
    print("  RAG Ops Quality Metrics Report")
    print("=" * 50)
    print(f"  Total Queries          : {report['total_queries']}")
    print(f"  Avg Response Latency   : {report['avg_latency_ms']} ms")
    print(f"  Citation Precision@{TOP_K}  : {report['citation_precision_at_k']:.2%}")
    print(f"  Critic Precision       : {report['critic_precision']:.2%}")
    print(f"  Avg Critic Score       : {report['avg_critic_score']:.2%}")
    print("=" * 50)

    # Write JSON report
    out_path = Path("metrics_report.json")
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\n✅ Report saved to {out_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(compute())
