# Azure migration evidence — 2026-11-03

This migration deployed the exact previous ZIP, without rebuilding from the dirty working tree. Full copy covers32 application tables and the Alembic head. constraints138 include9 equivalent unbounded-varchar-array/text-cast deparse differences, normalized narrowly with negative tests. Row data hashes are NOT normalized. Original row PK/hash checks after acceptance confirmed preservation.

Existing-state HTTPS16 requests and new core HTTPS61 requests/18 groups are separate fresh runs. Tool tests6 are local non-DB tests. Historical whole PostgreSQL368/local HTTP33 and previous related92 are not rerun or summed. No B/AI/RAG/Fabric/sending engine integration is claimed.

Two initial copy attempts returned to the old service before target public writes began; their errors are not counted as successful runs. The final latest frozen copy succeeded. Shared group DO_NOT_DELETE was changed only after the user's explicit exception approval and restored with identical properties. Empty old plan disappeared with deletion of its final app; all3 old resource GETs subsequently returned404. Actual DB backups/config/roles/credentials are DPAPI-encrypted or private and NOT included in this evidence directory.
