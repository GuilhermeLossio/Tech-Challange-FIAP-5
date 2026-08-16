IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'ecloe_features')
BEGIN
    EXEC(N'CREATE SCHEMA ecloe_features');
END;
GO

IF OBJECT_ID(N'ecloe_features.schema_migrations', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_features.schema_migrations (
        migration_id NVARCHAR(160) NOT NULL CONSTRAINT pk_features_schema_migrations PRIMARY KEY,
        applied_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_features_schema_migrations_applied_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00'))
    );
END;
GO

IF OBJECT_ID(N'ecloe_features.seed_runs', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_features.seed_runs (
        seed_run_id NVARCHAR(80) NOT NULL CONSTRAINT pk_features_seed_runs PRIMARY KEY,
        seed_value INT NOT NULL,
        subject_count INT NOT NULL,
        market_interaction_count INT NOT NULL,
        pay_interaction_count INT NOT NULL,
        payload_checksum CHAR(64) NOT NULL,
        data_origin NVARCHAR(32) NOT NULL CONSTRAINT df_features_seed_runs_origin DEFAULT N'synthetic_seed',
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_features_seed_runs_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT ck_features_seed_runs_counts CHECK (subject_count > 0 AND market_interaction_count >= 0 AND pay_interaction_count >= 0),
        CONSTRAINT ck_features_seed_runs_origin CHECK (data_origin = N'synthetic_seed')
    );
END;
GO

IF OBJECT_ID(N'ecloe_features.feature_snapshots', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_features.feature_snapshots (
        snapshot_id NVARCHAR(100) NOT NULL CONSTRAINT pk_features_feature_snapshots PRIMARY KEY,
        seed_run_id NVARCHAR(80) NOT NULL,
        subject_key NVARCHAR(80) NOT NULL,
        surface NVARCHAR(16) NOT NULL,
        features_json NVARCHAR(MAX) NOT NULL,
        data_origin NVARCHAR(32) NOT NULL CONSTRAINT df_features_snapshots_origin DEFAULT N'synthetic_seed',
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT df_features_snapshots_created_at DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
        CONSTRAINT fk_features_snapshots_seed_run FOREIGN KEY (seed_run_id) REFERENCES ecloe_features.seed_runs(seed_run_id),
        CONSTRAINT uq_features_snapshots_subject_surface UNIQUE (seed_run_id, subject_key, surface),
        CONSTRAINT ck_features_snapshots_surface CHECK (surface IN (N'market', N'pay')),
        CONSTRAINT ck_features_snapshots_json CHECK (ISJSON(features_json) = 1),
        CONSTRAINT ck_features_snapshots_origin CHECK (data_origin = N'synthetic_seed')
    );
END;
GO

IF OBJECT_ID(N'ecloe_features.synthetic_interactions', N'U') IS NULL
BEGIN
    CREATE TABLE ecloe_features.synthetic_interactions (
        event_id NVARCHAR(128) NOT NULL CONSTRAINT pk_features_synthetic_interactions PRIMARY KEY,
        seed_run_id NVARCHAR(80) NOT NULL,
        subject_key NVARCHAR(80) NOT NULL,
        decision_id NVARCHAR(80) NOT NULL,
        surface NVARCHAR(16) NOT NULL,
        candidate_id NVARCHAR(80) NOT NULL,
        position INT NOT NULL,
        event_type NVARCHAR(24) NOT NULL,
        terminal BIT NOT NULL,
        reward DECIMAL(4, 2) NULL,
        occurred_at DATETIMEOFFSET(7) NOT NULL,
        data_origin NVARCHAR(32) NOT NULL CONSTRAINT df_features_interactions_origin DEFAULT N'synthetic_seed',
        CONSTRAINT fk_features_interactions_seed_run FOREIGN KEY (seed_run_id) REFERENCES ecloe_features.seed_runs(seed_run_id),
        CONSTRAINT ck_features_interactions_surface CHECK (surface IN (N'market', N'pay')),
        CONSTRAINT ck_features_interactions_position CHECK (position BETWEEN 1 AND 20),
        CONSTRAINT ck_features_interactions_reward CHECK (reward IS NULL OR reward IN (0.00, 1.00)),
        CONSTRAINT ck_features_interactions_terminal CHECK ((terminal = 0 AND reward IS NULL) OR (terminal = 1 AND reward IS NOT NULL)),
        CONSTRAINT ck_features_interactions_origin CHECK (data_origin = N'synthetic_seed')
    );
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'ix_features_interactions_subject'
        AND object_id = OBJECT_ID(N'ecloe_features.synthetic_interactions')
)
BEGIN
    CREATE INDEX ix_features_interactions_subject
        ON ecloe_features.synthetic_interactions (subject_key, occurred_at);
END;
GO

IF NOT EXISTS (
    SELECT 1 FROM ecloe_features.schema_migrations
    WHERE migration_id = N'20260811_recommendation_features_v2'
)
BEGIN
    INSERT INTO ecloe_features.schema_migrations (migration_id)
    VALUES (N'20260811_recommendation_features_v2');
END;
GO
