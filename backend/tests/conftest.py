from hypothesis import HealthCheck, settings

# Property tests assert determinism and invariants, not speed; a loaded CI machine must not fail them.
settings.register_profile("gauntlet", deadline=None, suppress_health_check=[HealthCheck.too_slow])
settings.load_profile("gauntlet")
