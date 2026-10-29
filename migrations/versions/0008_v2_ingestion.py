"""Add Binance-only v2 registry and ingestion without changing legacy records."""

from alembic import op

revision = "0008_v2_ingestion"
down_revision = "0007_memos"
branch_labels = None
depends_on = None

DDL = r"""
CREATE TABLE v2_instruments (
 instrument_id varchar(109) PRIMARY KEY,
 venue_id varchar(32) NOT NULL CHECK (venue_id = 'binance'),
 market varchar(8) NOT NULL CHECK (market = 'spot'),
 source_symbol varchar(64) NOT NULL CHECK (source_symbol ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
 base_asset varchar(32) NOT NULL CHECK (base_asset ~ '^[A-Z0-9][A-Z0-9._-]{0,31}$'),
 quote_asset varchar(32) NOT NULL CHECK (quote_asset ~ '^[A-Z0-9][A-Z0-9._-]{0,31}$'),
 display_name varchar(80) NOT NULL CHECK (length(display_name) BETWEEN 1 AND 80 AND display_name
!~ '[[:cntrl:]]'),
 trade_id_order varchar(8) NOT NULL CHECK (trade_id_order = 'numeric'),
 adapter varchar(32) NOT NULL CHECK (adapter = 'binance_daily'),
 semantic_sha256 varchar(64) NOT NULL CHECK (semantic_sha256 ~ '^[0-9a-f]{64}$'),
 enabled boolean NOT NULL, revision integer NOT NULL CHECK (revision >= 0),
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 CHECK (instrument_id = 'binance:spot:' || source_symbol),
 UNIQUE (venue_id,market,source_symbol), UNIQUE (instrument_id,semantic_sha256)
);
CREATE INDEX ix_v2_instruments_enabled ON v2_instruments(enabled,instrument_id);
CREATE INDEX ix_v2_instruments_assets ON v2_instruments(base_asset,quote_asset,instrument_id);
CREATE TABLE v2_operations (
 operation varchar(32) NOT NULL, protocol varchar(48) NOT NULL,
 idempotency_key varchar(128) NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9_.-]{1,128}$'),
 request_sha256 varchar(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
 resource_id uuid, response_json jsonb NOT NULL,
 created_at timestamptz NOT NULL,
 PRIMARY KEY(operation,protocol,idempotency_key)
);
CREATE TABLE v2_ingestion_submissions (
 submission_id uuid PRIMARY KEY,
 request_sha256 varchar(64) NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
 request_json jsonb NOT NULL, contract varchar(48) NOT NULL CHECK (contract = 'daily-ingestion-v2'),
 execution_sha256 varchar(64) NOT NULL CHECK (execution_sha256 ~ '^[0-9a-f]{64}$'),
 lock_sha256 varchar(64) NOT NULL CHECK (lock_sha256 ~ '^[0-9a-f]{64}$'),
 transform_version varchar(48) NOT NULL CHECK (transform_version = 'binance-spot-trades-v2'),
 from_date date NOT NULL, before_date date NOT NULL,
 instrument_count integer NOT NULL CHECK (instrument_count BETWEEN 1 AND 2),
 child_count integer NOT NULL CHECK (child_count BETWEEN 1 AND 62), created_at timestamptz NOT NULL,
 CHECK (from_date >= DATE '1970-01-01' AND from_date < before_date AND before_date <= DATE
'9999-12-31'),
 CHECK (child_count = instrument_count * (before_date-from_date))
);
CREATE TABLE v2_canonical_imports (
 import_id uuid PRIMARY KEY, instrument_id varchar(109) NOT NULL,
 semantic_sha256 varchar(64) NOT NULL, trade_date date NOT NULL,
 metadata_json jsonb NOT NULL,
 metadata_sha256 varchar(64) NOT NULL CHECK (metadata_sha256 ~ '^[0-9a-f]{64}$'),
 source_sha256 varchar(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
 format varchar(8) NOT NULL CHECK (format IN ('csv','parquet')),
 declared_bytes bigint NOT NULL CHECK (declared_bytes BETWEEN 1 AND 4294967296),
 received_bytes bigint NOT NULL CHECK (received_bytes >= 0 AND received_bytes <= declared_bytes),
 generation_id uuid NOT NULL UNIQUE, source_relative_path text NOT NULL UNIQUE,
 state varchar(16) NOT NULL CHECK (state IN
('staging','queued','running','retry_wait','succeeded','failed','cancelled')),
 revision integer NOT NULL CHECK (revision >= 0), staging_owner uuid, staging_lease_until
timestamptz,
 submission_id uuid UNIQUE REFERENCES v2_ingestion_submissions(submission_id),
 error_code varchar(64), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 FOREIGN KEY(instrument_id,semantic_sha256) REFERENCES
v2_instruments(instrument_id,semantic_sha256),
 CHECK (trade_date BETWEEN DATE '1970-01-01' AND DATE '9999-12-30'),
 CHECK ((state='staging') = (staging_owner IS NOT NULL AND staging_lease_until IS NOT NULL)),
 CHECK (state='staging' OR (staging_owner IS NULL AND staging_lease_until IS NULL))
);
CREATE INDEX ix_v2_imports_stage ON v2_canonical_imports(state,staging_lease_until,import_id);
CREATE TABLE v2_dataset_versions (
 dataset_version_id varchar(64) PRIMARY KEY CHECK (dataset_version_id ~ '^[0-9a-f]{64}$'),
 instrument_id varchar(109) NOT NULL, semantic_sha256 varchar(64) NOT NULL, trade_date date NOT
NULL,
 source_sha256 varchar(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
 metadata_sha256 varchar(64) NOT NULL CHECK (metadata_sha256 ~ '^[0-9a-f]{64}$'),
 logical_sha256 varchar(64) NOT NULL CHECK (logical_sha256 ~ '^[0-9a-f]{64}$'),
 manifest_sha256 varchar(64) NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
 schema_version varchar(48) NOT NULL CHECK (schema_version = 'spot-trades-v2'),
 transform_version varchar(48) NOT NULL CHECK (transform_version = 'binance-spot-trades-v2'),
 lock_sha256 varchar(64) NOT NULL CHECK (lock_sha256 ~ '^[0-9a-f]{64}$'),
 manifest_relative_path text NOT NULL UNIQUE,
 row_count bigint NOT NULL CHECK (row_count BETWEEN 1 AND 20000000),
 observed_from timestamptz NOT NULL, observed_through timestamptz NOT NULL, published_at
timestamptz NOT NULL,
 FOREIGN KEY(instrument_id,semantic_sha256) REFERENCES
v2_instruments(instrument_id,semantic_sha256),
 CHECK (trade_date BETWEEN DATE '1970-01-01' AND DATE '9999-12-30'),
 CHECK (observed_from <= observed_through AND observed_from >= trade_date::timestamp AT TIME
ZONE 'UTC'
 AND observed_through < (trade_date + 1)::timestamp AT TIME ZONE 'UTC')
);
CREATE INDEX ix_v2_datasets_day ON v2_dataset_versions(instrument_id,trade_date,dataset_version_id);
CREATE TABLE v2_ingestion_jobs (
 job_id uuid PRIMARY KEY, submission_id uuid NOT NULL REFERENCES
v2_ingestion_submissions(submission_id),
 instrument_id varchar(109) NOT NULL, semantic_sha256 varchar(64) NOT NULL, instrument_snapshot
jsonb NOT NULL,
 trade_date date NOT NULL CHECK (trade_date BETWEEN DATE '1970-01-01' AND DATE '9999-12-30'),
 source_mode varchar(16) NOT NULL CHECK (source_mode IN ('official','canonical')),
 import_id uuid UNIQUE REFERENCES v2_canonical_imports(import_id),
 state varchar(16) NOT NULL CHECK (state IN
('queued','running','retry_wait','succeeded','failed','cancelled')),
 revision integer NOT NULL CHECK (revision >= 0),
 attempt_count integer NOT NULL CHECK (attempt_count BETWEEN 0 AND 3),
 fencing_token bigint NOT NULL CHECK (fencing_token >= 0), owner uuid, lease_until timestamptz,
 eligible_at timestamptz NOT NULL, cancel_requested boolean NOT NULL,
 result_version varchar(64) REFERENCES v2_dataset_versions(dataset_version_id), error_code
varchar(64),
 created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
 FOREIGN KEY(instrument_id,semantic_sha256) REFERENCES
v2_instruments(instrument_id,semantic_sha256),
 UNIQUE(submission_id,instrument_id,trade_date),
 CHECK ((source_mode='canonical') = (import_id IS NOT NULL)),
 CHECK ((state='running') = (owner IS NOT NULL AND lease_until IS NOT NULL)),
 CHECK (state='running' OR (owner IS NULL AND lease_until IS NULL)),
 CHECK ((state='succeeded') = (result_version IS NOT NULL))
);
CREATE INDEX ix_v2_jobs_claim ON v2_ingestion_jobs(state,eligible_at,lease_until,job_id);
CREATE INDEX ix_v2_jobs_submission ON v2_ingestion_jobs(submission_id,job_id);
CREATE TABLE v2_ingestion_attempts (
 job_id uuid NOT NULL REFERENCES v2_ingestion_jobs(job_id),
 attempt_number integer NOT NULL CHECK (attempt_number BETWEEN 1 AND 3),
 fencing_token bigint NOT NULL CHECK (fencing_token > 0), owner uuid NOT NULL,
 execution_sha256 varchar(64) NOT NULL CHECK (execution_sha256 ~ '^[0-9a-f]{64}$'),
 started_at timestamptz NOT NULL, ended_at timestamptz,
 outcome varchar(16) NOT NULL CHECK (outcome IN
('running','succeeded','transient','permanent','expired','cancelled')),
 error_code varchar(64), PRIMARY KEY(job_id,attempt_number), UNIQUE(job_id,fencing_token),
 CHECK ((outcome='running') = (ended_at IS NULL))
);
CREATE TABLE v2_storage_reservations (
 reservation_id uuid PRIMARY KEY, import_id uuid REFERENCES v2_canonical_imports(import_id),
 job_id uuid REFERENCES v2_ingestion_jobs(job_id), fencing_token bigint,
 kind varchar(16) NOT NULL CHECK (kind IN ('source','output','scratch')),
 reserved_bytes bigint NOT NULL CHECK (reserved_bytes >= 0),
 retained_bytes bigint NOT NULL CHECK (retained_bytes >= 0),
 ceiling_bytes bigint NOT NULL CHECK (ceiling_bytes > 0),
 state varchar(16) NOT NULL CHECK (state IN ('reserved','retained','released')),
 relative_path text NOT NULL UNIQUE, created_at timestamptz NOT NULL, updated_at timestamptz NOT
NULL,
 CHECK (reserved_bytes+retained_bytes <= ceiling_bytes),
 CHECK ((kind='source' AND import_id IS NOT NULL AND job_id IS NULL AND fencing_token IS NULL)
 OR (kind IN ('output','scratch') AND job_id IS NOT NULL AND fencing_token IS NOT NULL AND
fencing_token > 0 AND import_id IS NULL)),
 CHECK (state <> 'released' OR (reserved_bytes=0 AND retained_bytes=0))
);
CREATE INDEX ix_v2_reservations_state ON v2_storage_reservations(state,reservation_id);
CREATE INDEX ix_v2_reservations_import ON v2_storage_reservations(import_id);
CREATE INDEX ix_v2_reservations_job ON v2_storage_reservations(job_id,fencing_token);
INSERT INTO v2_instruments
 (instrument_id,venue_id,market,source_symbol,base_asset,quote_asset,display_name,
 trade_id_order,adapter,semantic_sha256,enabled,revision,created_at,updated_at)
 VALUES
 ('binance:spot:BTCUSDT','binance','spot','BTCUSDT','BTC','USDT','BTC/USDT','numeric',
'binance_daily','975394dc1f606b56e7fc9d5823b8c4869fa9eeaea7d35315d86a8e46481def6b',true,0,clock_timestamp(),clock_timestamp()),
 ('binance:spot:ETHUSDT','binance','spot','ETHUSDT','ETH','USDT','ETH/USDT','numeric',
'binance_daily','5ebe81a7ef38b3bf3710bb776b99b8f76789d2540c01609f723f34f3fa3ff463',true,0,clock_timestamp(),clock_timestamp());
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    raise RuntimeError("V2 ingestion is forward-only; restore a verified backup separately")
