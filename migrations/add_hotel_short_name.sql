-- Agregar columna short_name a la tabla de hoteles
ALTER TABLE entities.hotels ADD COLUMN IF NOT EXISTS short_name VARCHAR(250);
