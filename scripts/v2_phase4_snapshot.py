"""Compare owned PostgreSQL dump/restores, including every non-system schema.

Adapted without changing comparison semantics from the previously exercised
artifacts/v2-phase4-20261030/closeout_snapshot.py (itself based on Phase 3).
Only restore-side temporary tables are used to normalize server-reparsed CHECKs.
"""

import hashlib
import uuid

import sqlalchemy as sa

NON_SYSTEM = "n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_'"


def row_digest(values):
    digest = hashlib.sha256()
    count = 0
    for value in values:
        data = value.encode("utf-8")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def snapshot(engine):
    quote = engine.dialect.identifier_preparer.quote
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
        c.execute(sa.text("SET TRANSACTION READ ONLY"))
        c.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
        foreign = c.execute(
            sa.text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE c.relkind='f' AND " + NON_SYSTEM
            )
        ).scalar_one()
        assert foreign == 0, (
            "Foreign-table data cannot be silently omitted from a verified local dump"
        )
        schemas = list(
            c.execute(
                sa.text(
                    "SELECT n.nspname FROM pg_namespace n WHERE "
                    + NON_SYSTEM
                    + " ORDER BY n.nspname"
                )
            ).scalars()
        )
        tables = list(
            c.execute(
                sa.text(
                    "SELECT n.nspname,c.relname,c.relkind FROM pg_class c JOIN pg_namespace n ON "
                    "n.oid=c.relnamespace WHERE c.relkind IN ('r','p','m') AND "
                    + NON_SYSTEM
                    + " ORDER BY n.nspname,c.relname"
                )
            )
        )
        values = {}
        for schema, table, kind in tables:
            result = (
                c.execution_options(stream_results=True)
                .execute(
                    sa.text(
                        "SELECT to_jsonb(t)::text FROM "
                        + quote(schema)
                        + "."
                        + quote(table)
                        + " t ORDER BY to_jsonb(t)::text"
                    )
                )
                .scalars()
            )
            values[schema + "." + table] = dict(row_digest(result), relation_kind=kind)
        sequences = {}
        for schema, name in c.execute(
            sa.text(
                "SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n ON "
                "n.oid=c.relnamespace WHERE c.relkind='S' AND "
                + NON_SYSTEM
                + " ORDER BY n.nspname,c.relname"
            )
        ):
            sequences[schema + "." + name] = list(
                c.execute(
                    sa.text("SELECT last_value,is_called FROM " + quote(schema) + "." + quote(name))
                ).one()
            )
        columns = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT n.nspname,c.relname,a.attnum,a.attname,format_type(a.atttypid,a.attty"
                    "pmod),a.attcollation::regcollation::text,a.attnotnull,a.attidentity,a.attgen"
                    "erated,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a JOIN pg_class c ON"
                    " c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN "
                    "pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE c.relkind IN "
                    "('r','p','m') AND a.attnum>0 AND NOT a.attisdropped AND "
                    + NON_SYSTEM
                    + " ORDER BY n.nspname,c.relname,a.attnum"
                )
            )
        ]
        constraints = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid),k.contype,k"
                    ".convalidated,k.conislocal,k.coninhcount,k.connoinherit,k.condeferrable,k.co"
                    "ndeferred FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN "
                    "pg_namespace n ON n.oid=c.relnamespace WHERE "
                    + NON_SYSTEM
                    + " ORDER BY n.nspname,c.relname,k.conname"
                )
            )
        ]
        indexes = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE "
                    "schemaname NOT IN ('pg_catalog','information_schema') AND schemaname !~ "
                    "'^pg_' ORDER BY schemaname,tablename,indexname"
                )
            )
        ]
        views = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT n.nspname,c.relname,c.relkind,pg_get_viewdef(c.oid,true) FROM "
                    "pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind IN "
                    "('v','m') AND " + NON_SYSTEM + " ORDER BY n.nspname,c.relname"
                )
            )
        ]
        functions = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_"
                    "functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON "
                    "n.oid=p.pronamespace WHERE p.prokind IN ('f','p') AND "
                    + NON_SYSTEM
                    + " ORDER BY n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)"
                )
            )
        ]
        enums = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT n.nspname,t.typname,e.enumsortorder,e.enumlabel FROM pg_type t JOIN "
                    "pg_namespace n ON n.oid=t.typnamespace JOIN pg_enum e ON e.enumtypid=t.oid "
                    "WHERE " + NON_SYSTEM + " ORDER BY n.nspname,t.typname,e.enumsortorder"
                )
            )
        ]
        large_objects = [
            [int(oid), row_digest([bytes(data).hex()])]
            for oid, data in c.execute(
                sa.text("SELECT oid,lo_get(oid) FROM pg_largeobject_metadata ORDER BY oid")
            )
        ]
        triggers = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid,true) FROM "
                    "pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON "
                    "n.oid=c.relnamespace WHERE NOT t.tgisinternal AND "
                    + NON_SYSTEM
                    + " ORDER BY n.nspname,c.relname,t.tgname"
                )
            )
        ]
        domains = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT "
                    "n.nspname,t.typname,k.conname,pg_get_constraintdef(k.oid),k.convalidated "
                    "FROM pg_constraint k JOIN pg_type t ON t.oid=k.contypid JOIN pg_namespace n "
                    "ON n.oid=t.typnamespace WHERE "
                    + NON_SYSTEM
                    + " ORDER BY n.nspname,t.typname,k.conname"
                )
            )
        ]
        extensions = [
            list(x)
            for x in c.execute(
                sa.text(
                    "SELECT e.extname,e.extversion,n.nspname FROM pg_extension e JOIN "
                    "pg_namespace n ON n.oid=e.extnamespace ORDER BY e.extname"
                )
            )
        ]
        return {
            "triggers": triggers,
            "domain_constraints": domains,
            "extensions": extensions,
            "schemas": schemas,
            "tables": values,
            "columns": columns,
            "constraints": constraints,
            "indexes": indexes,
            "sequences": sequences,
            "views": views,
            "functions": functions,
            "enums": enums,
            "large_objects": large_objects,
        }


def exact_except_constraints(before, after):
    assert {k: v for k, v in before.items() if k != "constraints"} == {
        k: v for k, v in after.items() if k != "constraints"
    }, "Restored non-system schema data/definitions differ"
    source = {tuple(x[:3]): x for x in before["constraints"]}
    target = {tuple(x[:3]): x for x in after["constraints"]}
    assert source.keys() == target.keys() and {k: v[4:] for k, v in source.items()} == {
        k: v[4:] for k, v in target.items()
    }, "Restored constraint identity/flags differ"
    return [
        (key, source[key][3], target[key][3]) for key in source if source[key][3] != target[key][3]
    ]


def compare(before, after, restored_engine):
    differences = exact_except_constraints(before, after)
    normalizations = []
    if not differences:
        return normalizations
    quote = restored_engine.dialect.identifier_preparer.quote
    # Only restore-side temporary tables are changed, never source rows/schema.
    with restored_engine.begin() as c:
        for (schema, table, name), source, target in differences:
            assert source.startswith("CHECK (") and target.startswith("CHECK ("), (
                "Only server-reparsed CHECK text normalization is permitted"
            )
            temporary = "p4_closeout_check_" + uuid.uuid4().hex
            c.exec_driver_sql(
                "CREATE TEMP TABLE "
                + quote(temporary)
                + " (LIKE "
                + quote(schema)
                + "."
                + quote(table)
                + ") ON COMMIT DROP"
            )
            c.exec_driver_sql(
                "ALTER TABLE " + quote(temporary) + " ADD CONSTRAINT proof_check " + source
            )
            parsed = c.execute(
                sa.text(
                    "SELECT pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON "
                    "c.oid=k.conrelid WHERE c.relnamespace=pg_my_temp_schema() AND "
                    "c.relname=:table AND k.conname='proof_check'"
                ),
                {"table": temporary},
            ).scalar_one()
            assert parsed == target, (
                "Restored CHECK is not exactly the server reparsing of source CHECK"
            )
            normalizations.append(
                {
                    "constraint": [schema, table, name],
                    "source": source,
                    "restored": target,
                    "server_reparse_equal": True,
                }
            )
    return normalizations
