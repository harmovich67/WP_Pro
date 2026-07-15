"""
License API - FastAPI application for managing licenses
Refactored to accept database path as parameter for integration with main app
"""
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from uuid import uuid4
import logging
import logging.handlers
import os

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Integer, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship


def _setup_dashboard_logging() -> logging.Logger:
    """Configure rotating file logger for the license dashboard."""
    log_dir = Path.home() / ".config" / "HarmulizerPro" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "dashboard.log"

    logger = logging.getLogger("license_api")
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


logger = _setup_dashboard_logging()

# Database models base
Base = declarative_base()


# Database Models
class License(Base):
    __tablename__ = "licenses"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    key = Column(String, unique=True, nullable=False, index=True)
    tier = Column(String, default="basic")  # free, basic, pro, enterprise
    email = Column(String, nullable=True, index=True)
    customer_name = Column(String, nullable=True)
    whatsapp = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    
    max_activations = Column(Integer, default=1)
    notes = Column(String, nullable=True)
    custom_features = Column(JSON, default=dict)
    last_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    activations = relationship("Activation", back_populates="license", cascade="all, delete-orphan")


class Activation(Base):
    __tablename__ = "activations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    license_id = Column(String, ForeignKey("licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    machine_id = Column(String, nullable=False, index=True)
    
    activated_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True, index=True)
    
    license = relationship("License", back_populates="activations")


# Pydantic Schemas
class LicenseCreate(BaseModel):
    tier: str = "basic"
    email: Optional[str] = None
    customer_name: Optional[str] = None
    whatsapp: Optional[str] = None
    days_valid: Optional[int] = 30
    max_activations: int = 1
    notes: Optional[str] = None
    custom_features: Optional[dict] = None


class LicenseUpdate(BaseModel):
    tier: Optional[str] = None
    email: Optional[str] = None
    customer_name: Optional[str] = None
    whatsapp: Optional[str] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    max_activations: Optional[int] = None
    notes: Optional[str] = None
    custom_features: Optional[dict] = None


class LicenseResponse(BaseModel):
    id: str
    key: str
    tier: str
    email: Optional[str]
    customer_name: Optional[str]
    whatsapp: Optional[str]
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool
    max_activations: int
    current_activations: int
    notes: Optional[str]
    custom_features: dict
    last_modified: datetime
    
    class Config:
        from_attributes = True


class VerifyRequest(BaseModel):
    license_key: str
    machine_id: str


class VerifyResponse(BaseModel):
    success: bool
    tier: Optional[str] = None
    expires_at: Optional[str] = None
    custom_features: Optional[dict] = None
    message: Optional[str] = None


class DeactivateRequest(BaseModel):
    license_key: str
    machine_id: str


class StatsResponse(BaseModel):
    total_licenses: int
    active_licenses: int
    expired_licenses: int
    by_tier: dict


# Helper functions
def generate_license_key(tier: str = "pro") -> str:
    """Generate a unique license key."""
    tier_prefix = {
        "free": "HMF",
        "basic": "HMB",
        "pro": "HMP",
        "enterprise": "HME"
    }.get(tier, "HMP")
    
    segments = []
    for _ in range(4):
        segment = uuid4().hex[:4].upper()
        segments.append(segment)
    
    return f"{tier_prefix}-{'-'.join(segments)}"


def create_app(db_path: str = "licenses.db") -> FastAPI:
    """
    Create and configure FastAPI application
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        Configured FastAPI application
    """
    logger.info(f"Initializing License API with database: {db_path}")
    # Create database engine
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Migration: add missing columns to existing databases
    with engine.connect() as conn:
        from sqlalchemy import text, inspect
        inspector = inspect(engine)
        existing_cols = [c["name"] for c in inspector.get_columns("licenses")]
        if "last_modified" not in existing_cols:
            conn.execute(text(
                "ALTER TABLE licenses ADD COLUMN last_modified DATETIME"
            ))
            conn.execute(text(
                "UPDATE licenses SET last_modified = created_at WHERE last_modified IS NULL"
            ))
            conn.commit()
            logger.info("Migration: added last_modified column to licenses table")
    
    # Create FastAPI app
    app = FastAPI(
        title="Harmulizer Pro License API",
        description="API for managing software licenses",
        version="1.0.0"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Admin token for authentication
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "admin_secret_token_2024")
    
    # Stats cache: (result_dict, timestamp)
    _stats_cache: list = [None, None]
    _STATS_CACHE_TTL = 5  # seconds
    
    # Database dependency
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    # Auth dependency
    def verify_admin(authorization: str = Header(None)):
        if not authorization or authorization != f"Bearer {ADMIN_TOKEN}":
            logger.warning("Unauthorized access attempt to admin endpoint")
            raise HTTPException(status_code=401, detail="Unauthorized")
        return True
    
    # Routes
    @app.get("/")
    def root():
        return {"message": "Harmulizer Pro License API", "status": "running"}
    
    @app.get("/api/stats", response_model=StatsResponse)
    def get_stats(db: Session = Depends(get_db), _: bool = Depends(verify_admin)):
        """Get license statistics (cached for 5 seconds)."""
        import time
        now_ts = time.time()
        if _stats_cache[0] is not None and (now_ts - _stats_cache[1]) < _STATS_CACHE_TTL:
            return _stats_cache[0]
        
        total = db.query(License).count()
        active = db.query(License).filter(License.is_active == True).count()
        
        now = datetime.utcnow()
        expired = db.query(License).filter(
            License.expires_at != None,
            License.expires_at < now
        ).count()
        
        # By tier
        by_tier = {}
        for tier in ["free", "basic", "pro", "enterprise"]:
            count = db.query(License).filter(License.tier == tier).count()
            by_tier[tier] = count
        
        result = StatsResponse(
            total_licenses=total,
            active_licenses=active,
            expired_licenses=expired,
            by_tier=by_tier
        )
        _stats_cache[0] = result
        _stats_cache[1] = now_ts
        return result
    
    @app.get("/api/licenses", response_model=List[LicenseResponse])
    def list_licenses(
        skip: int = 0,
        limit: int = 50,
        tier: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        db: Session = Depends(get_db),
        _: bool = Depends(verify_admin)
    ):
        """List licenses with optional filtering and pagination (default page size: 50)."""
        query = db.query(License)
        
        if tier:
            query = query.filter(License.tier == tier)
        if is_active is not None:
            query = query.filter(License.is_active == is_active)
        if search:
            like = f"%{search}%"
            query = query.filter(
                License.key.ilike(like) |
                License.email.ilike(like) |
                License.customer_name.ilike(like)
            )
        
        licenses = query.offset(skip).limit(limit).all()
        
        result = []
        for lic in licenses:
            active_count = db.query(Activation).filter(
                Activation.license_id == lic.id,
                Activation.is_active == True
            ).count()
            
            result.append(LicenseResponse(
                id=lic.id,
                key=lic.key,
                tier=lic.tier,
                email=lic.email,
                customer_name=lic.customer_name,
                whatsapp=lic.whatsapp,
                created_at=lic.created_at,
                expires_at=lic.expires_at,
                is_active=lic.is_active,
                max_activations=lic.max_activations,
                current_activations=active_count,
                notes=lic.notes,
                custom_features=lic.custom_features or {},
                last_modified=lic.last_modified
            ))
        
        return result
    
    @app.post("/api/licenses", response_model=LicenseResponse)
    def create_license(
        data: LicenseCreate,
        db: Session = Depends(get_db),
        _: bool = Depends(verify_admin)
    ):
        """Create a new license."""
        key = generate_license_key(data.tier)
        
        expires_at = None
        if data.days_valid:
            expires_at = datetime.utcnow() + timedelta(days=data.days_valid)
        
        license = License(
            key=key,
            tier=data.tier,
            email=data.email,
            customer_name=data.customer_name,
            whatsapp=data.whatsapp,
            expires_at=expires_at,
            max_activations=data.max_activations,
            notes=data.notes,
            custom_features=data.custom_features or {}
        )
        
        db.add(license)
        db.commit()
        db.refresh(license)
        
        _stats_cache[0] = None  # Invalidate cache
        logger.info(f"License created: {license.key} (tier={data.tier}, email={data.email})")
        
        return LicenseResponse(
            id=license.id,
            key=license.key,
            tier=license.tier,
            email=license.email,
            customer_name=license.customer_name,
            whatsapp=license.whatsapp,
            created_at=license.created_at,
            expires_at=license.expires_at,
            is_active=license.is_active,
            max_activations=license.max_activations,
            current_activations=0,
            notes=license.notes,
            custom_features=license.custom_features or {},
            last_modified=license.last_modified
        )
    
    @app.get("/api/licenses/{license_id}", response_model=LicenseResponse)
    def get_license(
        license_id: str,
        db: Session = Depends(get_db),
        _: bool = Depends(verify_admin)
    ):
        """Get a specific license."""
        license = db.query(License).filter(License.id == license_id).first()
        if not license:
            raise HTTPException(status_code=404, detail="License not found")
        
        active_count = db.query(Activation).filter(
            Activation.license_id == license.id,
            Activation.is_active == True
        ).count()
        
        return LicenseResponse(
            id=license.id,
            key=license.key,
            tier=license.tier,
            email=license.email,
            customer_name=license.customer_name,
            whatsapp=license.whatsapp,
            created_at=license.created_at,
            expires_at=license.expires_at,
            is_active=license.is_active,
            max_activations=license.max_activations,
            current_activations=active_count,
            notes=license.notes,
            custom_features=license.custom_features or {},
            last_modified=license.last_modified
        )
    
    @app.put("/api/licenses/{license_id}", response_model=LicenseResponse)
    def update_license(
        license_id: str,
        data: LicenseUpdate,
        db: Session = Depends(get_db),
        _: bool = Depends(verify_admin)
    ):
        """Update a license."""
        license = db.query(License).filter(License.id == license_id).first()
        if not license:
            raise HTTPException(status_code=404, detail="License not found")
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(license, key, value)
        
        # Update last_modified timestamp
        license.last_modified = datetime.utcnow()
        
        db.commit()
        db.refresh(license)
        
        _stats_cache[0] = None  # Invalidate cache
        
        active_count = db.query(Activation).filter(
            Activation.license_id == license.id,
            Activation.is_active == True
        ).count()
        
        return LicenseResponse(
            id=license.id,
            key=license.key,
            tier=license.tier,
            email=license.email,
            customer_name=license.customer_name,
            whatsapp=license.whatsapp,
            created_at=license.created_at,
            expires_at=license.expires_at,
            is_active=license.is_active,
            max_activations=license.max_activations,
            current_activations=active_count,
            notes=license.notes,
            custom_features=license.custom_features or {},
            last_modified=license.last_modified
        )
    
    @app.delete("/api/licenses/{license_id}")
    def delete_license(
        license_id: str,
        db: Session = Depends(get_db),
        _: bool = Depends(verify_admin)
    ):
        """Delete a license (cascade deletes activations)."""
        license = db.query(License).filter(License.id == license_id).first()
        if not license:
            raise HTTPException(status_code=404, detail="License not found")
        
        db.delete(license)
        db.commit()
        _stats_cache[0] = None  # Invalidate cache
        logger.info(f"License deleted: {license_id}")
        
        return {"message": "License deleted successfully"}
    
    # Public verification endpoint (no admin auth needed)
    @app.post("/api/verify", response_model=VerifyResponse)
    def verify_license(data: VerifyRequest, db: Session = Depends(get_db)):
        """Verify and activate a license."""
        license = db.query(License).filter(License.key == data.license_key).first()
        
        if not license:
            return VerifyResponse(success=False, message="مفتاح الترخيص غير صالح")
        
        # Check existing activation for this machine FIRST
        existing = db.query(Activation).filter(
            Activation.license_id == license.id,
            Activation.machine_id == data.machine_id
        ).first()
        
        # If machine was previously activated, allow reactivation
        if existing:
            # Check expiration
            if license.expires_at and license.expires_at < datetime.utcnow():
                return VerifyResponse(success=False, message="الترخيص منتهي الصلاحية")
            
            # Reactivate the license if it was deactivated
            if not license.is_active:
                license.is_active = True
            
            # Update last seen
            existing.last_seen = datetime.utcnow()
            existing.is_active = True
            db.commit()
            
            return VerifyResponse(
                success=True,
                tier=license.tier,
                expires_at=license.expires_at.isoformat() if license.expires_at else None,
                custom_features=license.custom_features or {}
            )
        
        # For new machines, check if license is active
        if not license.is_active:
            return VerifyResponse(success=False, message="الترخيص معطل")
        
        # Check expiration
        if license.expires_at and license.expires_at < datetime.utcnow():
            return VerifyResponse(success=False, message="الترخيص منتهي الصلاحية")
        
        # Check max activations
        active_count = db.query(Activation).filter(
            Activation.license_id == license.id,
            Activation.is_active == True
        ).count()
        
        if active_count >= license.max_activations:
            return VerifyResponse(
                success=False,
                message=f"تم استنفاد عدد التفعيلات المسموح ({license.max_activations})"
            )
        
        # Create new activation
        activation = Activation(
            license_id=license.id,
            machine_id=data.machine_id
        )
        db.add(activation)
        db.commit()
        
        return VerifyResponse(
            success=True,
            tier=license.tier,
            expires_at=license.expires_at.isoformat() if license.expires_at else None,
            custom_features=license.custom_features or {}
        )
    
    @app.post("/api/deactivate")
    def deactivate_license(data: DeactivateRequest, db: Session = Depends(get_db)):
        """Deactivate a license from a machine."""
        license = db.query(License).filter(License.key == data.license_key).first()
        
        if not license:
            return {"success": False, "message": "مفتاح الترخيص غير صالح"}

        activation = db.query(Activation).filter(
            Activation.license_id == license.id,
            Activation.machine_id == data.machine_id
        ).first()

        if activation:
            activation.is_active = False
            db.commit()

        return {"success": True, "message": "تم إلغاء التفعيل بنجاح"}
    
    # Activation management endpoints
    @app.get("/api/licenses/{license_id}/activations")
    def get_license_activations(
        license_id: str,
        db: Session = Depends(get_db),
        _: bool = Depends(verify_admin)
    ):
        """Get all activations for a license."""
        license = db.query(License).filter(License.id == license_id).first()
        if not license:
            raise HTTPException(status_code=404, detail="License not found")
        
        activations = db.query(Activation).filter(
            Activation.license_id == license_id
        ).all()
        
        return [
            {
                "id": act.id,
                "machine_id": act.machine_id,
                "activated_at": act.activated_at.isoformat(),
                "last_seen": act.last_seen.isoformat(),
                "is_active": act.is_active
            }
            for act in activations
        ]
    
    @app.delete("/api/activations/{activation_id}")
    def deactivate_activation(
        activation_id: str,
        db: Session = Depends(get_db),
        _: bool = Depends(verify_admin)
    ):
        """Deactivate a specific activation."""
        activation = db.query(Activation).filter(Activation.id == activation_id).first()
        if not activation:
            raise HTTPException(status_code=404, detail="Activation not found")
        
        activation.is_active = False
        db.commit()
        
        return {"message": "Activation deactivated successfully"}
    
    return app
