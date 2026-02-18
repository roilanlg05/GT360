CREATE SCHEMA IF NOT EXISTS ratings;

CREATE TABLE IF NOT EXISTS ratings.driver_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trip_id UUID NOT NULL,
    trip_hash TEXT NOT NULL,
    driver_id UUID REFERENCES entities.drivers(id) ON DELETE SET NULL,
    crew_id UUID REFERENCES entities.users(id) ON DELETE SET NULL,
    score SMALLINT NOT NULL,
    comment TEXT,
    stamps JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_crew_trip_rating UNIQUE (crew_id, trip_id),
    CONSTRAINT valid_score CHECK (score >= 1 AND score <= 5)
);

CREATE INDEX IF NOT EXISTS idx_driver_ratings_driver_id ON ratings.driver_ratings(driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_ratings_crew_id ON ratings.driver_ratings(crew_id);
CREATE INDEX IF NOT EXISTS idx_driver_ratings_trip_id ON ratings.driver_ratings(trip_id);
CREATE INDEX IF NOT EXISTS idx_driver_ratings_created_at ON ratings.driver_ratings(created_at);
