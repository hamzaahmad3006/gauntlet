from hypothesis import HealthCheck, settings

# Property tests assert determinism and invariants, not speed; a loaded CI machine must not fail them.
settings.register_profile("gauntlet", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("gauntlet")


async def reset_schema_if_postgres() -> None:
    """With TEST_DATABASE_URL (CI's PostgreSQL service), every test starts from an empty schema."""
    import os

    if not os.environ.get("TEST_DATABASE_URL"):
        return
    from gauntlet.context import ctx
    from gauntlet.db.tables import metadata

    async with ctx().engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)


def database_url(tmp_path, name: str) -> str:
    import os

    return os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}"
