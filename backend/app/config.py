"""Settings for the BlueProof backend.

Every external dependency (Llama, Sentinel-2, M-Pesa) has a mock mode, so the
whole verification and payment flow runs with no credentials. Fill the .env file
to switch a service to live without touching the code.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The development secret. Refused at startup when ENVIRONMENT=production,
# because a token signed with a key printed in a public repository is not a
# credential.
DEV_SECRET = "dev-only-not-a-secret"


class Settings(BaseSettings):
    # backend/.env wherever the server is started from; environment variables
    # still take precedence over the file.
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore")

    app_name: str = "BlueProof API"
    environment: str = "dev"  # dev | production
    database_url: str = "sqlite:///./blueproof.db"
    # Comma separated. "*" is safe here because auth is a bearer token, never a
    # cookie, but a pilot should still name its two origins.
    cors_origins: str = "*"

    # ---- Auth ---------------------------------------------------------------
    secret_key: str = DEV_SECRET
    token_ttl_hours: int = 12
    # Failed PIN attempts before a phone number is locked, and for how long.
    max_login_attempts: int = 5
    lockout_minutes: int = 15
    # Seeds the Tudor Creek demo site and demo people with known PINs. Off in
    # production unless explicitly asked for.
    demo_seed: bool | None = None
    # Production bootstrap: the first admin, created once if no admin exists.
    admin_phone: str | None = None
    admin_pin: str | None = None
    admin_name: str = "BlueProof admin"

    # ---- Evidence -----------------------------------------------------------
    photo_dir: str = "./data/photos"
    max_photo_bytes: int = 8 * 1024 * 1024
    # How far from the registered plot coordinate a submission may be taken.
    # Consumer GPS under mangrove canopy is off by tens of metres; this is set
    # to catch a photo taken in town, not to police a monitor's footing.
    geofence_radius_m: float = 150.0
    # A submission without a GPS fix is escalated rather than paid.
    require_gps: bool = True
    # One paid submission per plot per window. Without this, a plot pays out
    # as many times a day as somebody is willing to press the button.
    min_days_between_paid_events: int = 7
    # Perceptual hash distance at or below which two photographs are treated
    # as the same image re-encoded. dHash on a 64 bit grid.
    near_duplicate_distance: int = 4
    # Days to keep a photograph after its submission is final. Blank keeps
    # them. The verdict and the photo hash stay in the record either way.
    photo_retention_days: int | None = None

    # ---- Llama --------------------------------------------------------------
    # Leave the url blank to use the built in mock verifier and assistant.
    llama_api_url: str | None = None
    llama_api_key: str | None = None
    # Llama 4 Scout: natively multimodal and the cheapest Llama vision model
    # on OpenRouter. On Groq the id is meta-llama/llama-4-scout-17b-16e-instruct.
    llama_model: str = "meta-llama/llama-4-scout"
    llama_timeout_s: float = 60.0
    # Ask the verifier this many times and use agreement as the confidence.
    # 3 costs 3x inference (cents per submission) and gives a confidence that
    # means something. With 3 samples, a 0.6 threshold means "a majority
    # agreed"; set MIN_VERIFICATION_CONFIDENCE=0.9 to require unanimity.
    verifier_samples: int = 3
    # corroborate: the model is told the declared species and asked if the
    #   photo is consistent (prompt v3). Measured 2026-09-24: Llama 3.2 11B
    #   agreed with all 20 wrong declarations it was given.
    # blind: the model is NOT told the declaration; it picks from the nine
    #   and code compares (prompt v4). Measure before switching.
    verifier_mode: str = "corroborate"  # corroborate | blind
    verifier_sample_temperature: float = 0.7
    # Escalate a submission that arrives without a plot marker photograph.
    require_marker: bool = False

    # ---- Sentinel-2 via Copernicus Data Space -------------------------------
    # Blank means the mock NDVI series.
    copernicus_client_id: str | None = None
    copernicus_client_secret: str | None = None
    copernicus_token_url: str = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    )
    copernicus_stats_url: str = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
    satellite_lookback_days: int = 90
    satellite_interval_days: int = 5

    # ---- M-Pesa B2C ---------------------------------------------------------
    # mock settles instantly; sandbox and production use Daraja B2C, which is
    # the API that sends money TO a person. STK Push asks a person to pay.
    mpesa_mode: str = "mock"  # mock | sandbox | production
    mpesa_consumer_key: str | None = None
    mpesa_consumer_secret: str | None = None
    mpesa_shortcode: str | None = None
    mpesa_initiator_name: str | None = None
    # The initiator password encrypted with Safaricom's public certificate. The
    # Daraja portal generates it; it is not the password itself.
    mpesa_security_credential: str | None = None
    # Public base URL of this API, for Safaricom's result callbacks.
    public_base_url: str | None = None
    # Safaricom does not sign callbacks. A long random token in the callback
    # URL, compared in constant time, is the standard mitigation.
    mpesa_callback_token: str | None = None

    # ---- Payment policy -----------------------------------------------------
    # KSh paid per verified monitoring event.
    payout_per_verified_event: float = 150.0
    # Verification confidence a verdict must reach to trigger payment.
    min_verification_confidence: float = 0.6

    # ASSUMPTION, NOT A MEASUREMENT. Tonnes of CO2 per hectare per year used for
    # the indicative sequestration figure. Kenyan mangrove literature spans a
    # wide range. Validate with KMFRI or a Plan Vivo methodology before any
    # figure derived from this is quoted to a funder or a buyer.
    co2_tonnes_per_ha_year: float = 3.0

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def seed_demo(self) -> bool:
        return (not self.is_production) if self.demo_seed is None else self.demo_seed

    def check(self) -> None:
        """Refuse to start in production with settings that would be unsafe."""
        if not self.is_production:
            return
        problems = []
        if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be set to a random string of 32+ characters")
        if self.mpesa_mode != "mock":
            for name in (
                "mpesa_consumer_key", "mpesa_consumer_secret", "mpesa_shortcode",
                "mpesa_initiator_name", "mpesa_security_credential",
                "public_base_url", "mpesa_callback_token",
            ):
                if not getattr(self, name):
                    problems.append(f"{name.upper()} is required when MPESA_MODE={self.mpesa_mode}")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


settings = Settings()
