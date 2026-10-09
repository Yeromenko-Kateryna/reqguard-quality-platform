CREATE TABLE IF NOT EXISTS public.analyses (
    run_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    status TEXT NOT NULL,
    original_input TEXT NOT NULL,
    analysis_payload JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analyses_status_valid
        CHECK (status IN ('completed', 'unsupported_fixture')),
    CONSTRAINT analyses_analysis_consistency
        CHECK (
            (status = 'completed'
                AND analysis_payload IS NOT NULL
                AND jsonb_typeof(analysis_payload) = 'object')
            OR
            (status = 'unsupported_fixture' AND analysis_payload IS NULL)
        )
);
