from sqlalchemy import (Column, Integer, String, Float, DateTime,
                        ForeignKey, Boolean, Text)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class Batch(Base):
    """One processed BPR document."""
    __tablename__ = "batches"

    id               = Column(Integer, primary_key=True)
    file_path        = Column(String(500))
    doc_nr           = Column(String(50))
    revision         = Column(String(20))
    project_code     = Column(String(50))
    batch_no         = Column(String(50))
    production_code  = Column(String(50))
    production_code_ds = Column(String(50))
    process_step     = Column(String(50))
    sap_material_nr  = Column(String(50))
    man_nr           = Column(String(50))
    doc_date         = Column(String(30))
    gqq_generated_at = Column(String(30))
    status           = Column(String(20), default="pending")
    created_at       = Column(DateTime, default=datetime.utcnow)
    processed_at     = Column(DateTime)

    pages       = relationship("Page",             back_populates="batch", cascade="all, delete-orphan")
    fields      = relationship("Field",            back_populates="batch", cascade="all, delete-orphan")
    signatures  = relationship("Signature",        back_populates="batch", cascade="all, delete-orphan")
    personnel   = relationship("Personnel",        back_populates="batch", cascade="all, delete-orphan")
    validations = relationship("ValidationResult", back_populates="batch", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    id         = Column(Integer, primary_key=True)
    batch_id   = Column(Integer, ForeignKey("batches.id"))
    page_num   = Column(Integer)
    section    = Column(String(100))
    raw_text   = Column(Text)
    image_path = Column(String(500))
    # Pixel dimensions of the image OCR ran on, so field boxes (stored in
    # that coordinate space) can be scaled to whatever size we display.
    ocr_width  = Column(Integer)
    ocr_height = Column(Integer)

    batch  = relationship("Batch", back_populates="pages")
    fields = relationship("Field", back_populates="page", cascade="all, delete-orphan")


class Field(Base):
    """Any extracted key/value pair from the document."""
    __tablename__ = "fields"

    id           = Column(Integer, primary_key=True)
    batch_id     = Column(Integer, ForeignKey("batches.id"))
    page_id      = Column(Integer, ForeignKey("pages.id"))
    section      = Column(String(100))
    field_name   = Column(String(200))
    raw_value    = Column(Text)
    parsed_value = Column(Text)
    unit         = Column(String(50))
    confidence   = Column(Float, default=0.0)
    # Bounding box of the value on the page (in the OCR image's pixel space).
    bbox_x       = Column(Integer)
    bbox_y       = Column(Integer)
    bbox_w       = Column(Integer)
    bbox_h       = Column(Integer)

    batch = relationship("Batch", back_populates="fields")
    page  = relationship("Page",  back_populates="fields")


class Signature(Base):
    """A Bearbeitet / Geprüft entry with Kürzel and date."""
    __tablename__ = "signatures"

    id         = Column(Integer, primary_key=True)
    batch_id   = Column(Integer, ForeignKey("batches.id"))
    section    = Column(String(100))
    role       = Column(String(50))   # "Bearbeitet" | "Geprüft"
    kuerzel    = Column(String(20))
    date       = Column(String(30))
    page_num   = Column(Integer)

    batch = relationship("Batch", back_populates="signatures")


class Personnel(Base):
    """Personnel listed on page 4 of the document."""
    __tablename__ = "personnel"

    id       = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id"))
    name     = Column(String(200))
    kuerzel  = Column(String(20))

    batch = relationship("Batch", back_populates="personnel")


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id              = Column(Integer, primary_key=True)
    batch_id        = Column(Integer, ForeignKey("batches.id"))
    rule_id         = Column(String(50))
    rule_name       = Column(String(200))
    severity        = Column(String(20))   # error | warning | info
    message         = Column(Text)
    field_name      = Column(String(200))
    page_num        = Column(Integer)
    section         = Column(String(100))
    flagged_at      = Column(DateTime, default=datetime.utcnow)
    is_resolved     = Column(Boolean, default=False)
    resolution_note = Column(Text)

    batch = relationship("Batch", back_populates="validations")
