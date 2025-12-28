"""
Migration: added CASCADE to Organization.manager_id

Generated: 2025-12-27T08:30:35.623843
"""

from psqlmodel.migrations import Migration


class Migration_20251227_083035(Migration):
    """
    added CASCADE to Organization.manager_id
    """

    version = "20251227_083035"
    message = "added CASCADE to Organization.manager_id"
    depends_on = None
    head_id = "e649f001-8cd4-4d84-96e7-51f2d97bcaed"

    def up(self, engine):
        """Apply migration (sync)."""
        engine.execute_sql("ALTER TABLE public.organizations DROP CONSTRAINT IF EXISTS fk_organizations_manager_id;")
        engine.execute_sql("""ALTER TABLE public.organizations DROP CONSTRAINT IF EXISTS fk_organizations_manager_id;
ALTER TABLE public.organizations ADD CONSTRAINT fk_organizations_manager_id FOREIGN KEY (manager_id) REFERENCES auth.managers(id) ON DELETE CASCADE;""")

    def down(self, engine):
        """Revert migration (sync)."""
        engine.execute_sql("ALTER TABLE public.organizations DROP CONSTRAINT IF EXISTS fk_organizations_manager_id;")
        engine.execute_sql("""ALTER TABLE public.organizations DROP CONSTRAINT IF EXISTS fk_organizations_manager_id;
ALTER TABLE public.organizations ADD CONSTRAINT fk_organizations_manager_id FOREIGN KEY (manager_id) REFERENCES auth.managers(id) ON DELETE SET NULL;""")