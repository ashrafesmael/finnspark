from datetime import datetime, date

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, JSON, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


# ---------------------------------------------------------------- Tenancy (7.1)

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    registration_date = Column(Date, default=date.today)
    status_id = Column(Integer, ForeignKey("organization_statuses.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    branches = relationship("Branch", back_populates="organization")


class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)

    organization = relationship("Organization", back_populates="branches")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(120), default="")
    last_name = Column(String(120), default="")
    photo = Column(String(500), nullable=True)
    position = Column(String(160), default="")
    phone = Column(String(60), default="")
    company = Column(String(200), default="")
    status_id = Column(Integer, ForeignKey("user_statuses.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    role_links = relationship("UserRole", back_populates="user")


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    name = Column(String(160), nullable=False)
    code_name = Column(String(80), nullable=False)
    is_constant = Column(Boolean, default=False)
    permissions = Column(JSON, default=list)


class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)

    user = relationship("User", back_populates="role_links")
    role = relationship("Role")


# ---------------------------------------------------------------- Reference enums (7.7)

class RefBase(Base):
    __abstract__ = True
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    code_name = Column(String(100), nullable=False)


class Gender(RefBase):
    __tablename__ = "genders"


class Country(RefBase):
    __tablename__ = "countries"


class Province(Base):
    __tablename__ = "provinces"
    id = Column(Integer, primary_key=True)
    country_id = Column(Integer, ForeignKey("countries.id"))
    name = Column(String(200))


class District(Base):
    __tablename__ = "districts"
    id = Column(Integer, primary_key=True)
    province_id = Column(Integer, ForeignKey("provinces.id"))
    name = Column(String(200))


class BusinessType(RefBase):
    __tablename__ = "business_types"


class BusinessIndustry(RefBase):
    __tablename__ = "business_industries"


class FieldType(RefBase):
    __tablename__ = "field_types"


class FormStatus(RefBase):
    __tablename__ = "form_statuses"


class CourseStatus(RefBase):
    __tablename__ = "course_statuses"


class ProgramStatus(RefBase):
    __tablename__ = "program_statuses"
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)


class ApplicantStatus(RefBase):
    __tablename__ = "applicant_statuses"


class UserStatus(RefBase):
    __tablename__ = "user_statuses"


class OrganizationStatus(RefBase):
    __tablename__ = "organization_statuses"


class AnnouncementStatus(RefBase):
    __tablename__ = "announcement_statuses"


class InvestmentStatus(RefBase):
    __tablename__ = "investment_statuses"


class InvestmentTier(RefBase):
    __tablename__ = "investment_tiers"


class InvestmentRound(RefBase):
    __tablename__ = "investment_rounds"


class SelectionStage(Base):
    __tablename__ = "selection_stages"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    name = Column(String(200))
    description = Column(Text, default="")
    order = Column(Integer, default=0)


class InvestmentStage(Base):
    __tablename__ = "investment_stages"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    name = Column(String(200))
    description = Column(Text, default="")
    order = Column(Integer, default=0)


class CommitteeLevel(Base):
    __tablename__ = "committee_levels"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    name = Column(String(250))
    order = Column(Integer, default=0)


class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    name = Column(String(200))


class Subindustry(Base):
    __tablename__ = "subindustries"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"))
    industry_id = Column(Integer, ForeignKey("business_industries.id"))
    name = Column(String(200))


# ---------------------------------------------------------------- Intake & selection (7.2)

class ApplicationForm(Base):
    __tablename__ = "application_forms"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    name_i18n = Column(JSON, default=dict)          # {"en": "...", "ar": ...}
    main_language = Column(String(10), default="en")
    form_description = Column(Text, default="")
    kind = Column(String(20), default="application")  # application | investment
    status_id = Column(Integer, ForeignKey("form_statuses.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    fields = relationship("ApplicationFormField", back_populates="form",
                          cascade="all, delete-orphan", order_by="ApplicationFormField.order")


class ApplicationFormField(Base):
    __tablename__ = "application_form_fields"
    id = Column(Integer, primary_key=True)
    application_form_id = Column(Integer, ForeignKey("application_forms.id"), nullable=False)
    name_i18n = Column(JSON, default=dict)
    field_type_id = Column(Integer, ForeignKey("field_types.id"))
    is_required = Column(Boolean, default=False)
    order = Column(Integer, default=0)

    form = relationship("ApplicationForm", back_populates="fields")
    options = relationship("ApplicationFormFieldOption", back_populates="field",
                           cascade="all, delete-orphan", order_by="ApplicationFormFieldOption.order")


class ApplicationFormFieldOption(Base):
    __tablename__ = "application_form_field_options"
    id = Column(Integer, primary_key=True)
    application_form_field_id = Column(Integer, ForeignKey("application_form_fields.id"), nullable=False)
    name_i18n = Column(JSON, default=dict)
    order = Column(Integer, default=0)

    field = relationship("ApplicationFormField", back_populates="options")


class ScoringForm(Base):
    __tablename__ = "scoring_forms"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    selection_stage_id = Column(Integer, ForeignKey("selection_stages.id"), nullable=True)
    is_for_graduation = Column(Boolean, default=False)
    name_i18n = Column(JSON, default=dict)
    main_language = Column(String(10), default="en")
    form_description = Column(Text, default="")
    status_id = Column(Integer, ForeignKey("form_statuses.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    questions = relationship("ScoringQuestion", back_populates="form",
                             cascade="all, delete-orphan", order_by="ScoringQuestion.order")


class ScoringQuestion(Base):
    __tablename__ = "scoring_questions"
    id = Column(Integer, primary_key=True)
    scoring_form_id = Column(Integer, ForeignKey("scoring_forms.id"), nullable=False)
    name = Column(String(300))
    description = Column(Text, default="")
    weightage = Column(Float, default=0.0)
    is_required = Column(Boolean, default=True)
    order = Column(Integer, default=0)

    form = relationship("ScoringForm", back_populates="questions")


class Applicant(Base):
    __tablename__ = "applicants"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    selection_stage_id = Column(Integer, ForeignKey("selection_stages.id"), nullable=True)
    status_id = Column(Integer, ForeignKey("applicant_statuses.id"))
    email = Column(String(255), default="")
    first_name = Column(String(120), default="")
    last_name = Column(String(120), default="")
    business_name = Column(String(255), default="")
    business_logo = Column(String(500), nullable=True)
    country_id = Column(Integer, ForeignKey("countries.id"))
    province_id = Column(Integer, ForeignKey("provinces.id"))
    district_id = Column(Integer, ForeignKey("districts.id"))
    industry_id = Column(Integer, ForeignKey("business_industries.id"))
    gender_id = Column(Integer, ForeignKey("genders.id"))
    age = Column(Integer, nullable=True)
    channel_id = Column(Integer, ForeignKey("channels.id"))
    average_score = Column(Float, default=None, nullable=True)
    registered = Column(Boolean, default=False)
    invited_at = Column(DateTime, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    application_date = Column(DateTime, default=datetime.utcnow)
    answers = Column(JSON, default=dict)          # {field_key: value}
    answer_labels = Column(JSON, default=dict)    # {field_key: label} captured at submission

    program = relationship("Program")
    stage = relationship("SelectionStage")
    status = relationship("ApplicantStatus")
    country = relationship("Country")


class Evaluation(Base):
    __tablename__ = "evaluations"
    id = Column(Integer, primary_key=True)
    scoring_form_id = Column(Integer, ForeignKey("scoring_forms.id"), nullable=False)
    applicant_id = Column(Integer, ForeignKey("applicants.id"), nullable=False)
    evaluator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    answers = Column(JSON, default=list)   # [{question_id, score}]
    total_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------- Programmes & delivery (7.3)

class ProgramType(Base):
    __tablename__ = "program_types"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    name = Column(String(200))
    duration_months = Column(Integer, nullable=True)


class Program(Base):
    __tablename__ = "programs"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_type_id = Column(Integer, ForeignKey("program_types.id"))
    name = Column(String(250))
    description = Column(Text, default="")
    status_id = Column(Integer, ForeignKey("program_statuses.id"))
    scoring_required = Column(Boolean, default=False)
    creation_date = Column(DateTime, default=datetime.utcnow)

    program_type = relationship("ProgramType")
    status = relationship("ProgramStatus")


class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"))
    applicant_id = Column(Integer, ForeignKey("applicants.id"), nullable=True)
    name = Column(String(255))
    logo = Column(String(500), nullable=True)
    type_id = Column(Integer, ForeignKey("business_types.id"))
    industry_id = Column(Integer, ForeignKey("business_industries.id"))
    graduation_status = Column(String(30), default="Not graduated")
    course_progress = Column(Float, default=0.0)
    course_score = Column(Float, default=0.0)
    average_evaluator_score = Column(Float, default=0.0)
    invested = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    program = relationship("Program")
    founders = relationship("BusinessFounder", back_populates="business", cascade="all, delete-orphan")
    mentor_links = relationship("Mentorship", back_populates="business", cascade="all, delete-orphan")


class BusinessFounder(Base):
    __tablename__ = "business_founders"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    first_name = Column(String(120), default="")
    last_name = Column(String(120), default="")
    email = Column(String(255), default="")
    gender_id = Column(Integer, ForeignKey("genders.id"))
    age = Column(Integer, nullable=True)
    position = Column(String(160), default="")

    business = relationship("Business", back_populates="founders")


class Mentorship(Base):
    __tablename__ = "mentorships"
    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    mentor_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    business = relationship("Business", back_populates="mentor_links")
    mentor = relationship("User")


class MentorReviewQuestion(Base):
    __tablename__ = "mentor_review_questions"
    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=False)
    text = Column(Text)
    order = Column(Integer, default=0)


class MentorConclusionQuestion(Base):
    __tablename__ = "mentor_conclusion_questions"
    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=False)
    text = Column(Text)
    order = Column(Integer, default=0)


class QuestionAnswer(Base):
    __tablename__ = "question_answers"
    id = Column(Integer, primary_key=True)
    question_kind = Column(String(20))  # review | conclusion
    question_id = Column(Integer, nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    mentor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    answer_text = Column(Text, default="")
    score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------- LMS (7.4)

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    name = Column(String(250))
    description = Column(Text, default="")
    language = Column(String(10), default="en")
    subtitle_languages = Column(JSON, default=list)
    status_id = Column(Integer, ForeignKey("course_statuses.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    modules = relationship("Module", back_populates="course", cascade="all, delete-orphan",
                           order_by="Module.order")


class Module(Base):
    __tablename__ = "modules"
    id = Column(Integer, primary_key=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    name = Column(String(250))
    description = Column(Text, default="")
    order = Column(Integer, default=0)

    course = relationship("Course", back_populates="modules")
    lessons = relationship("Lesson", back_populates="module", cascade="all, delete-orphan",
                           order_by="Lesson.order")


class Lesson(Base):
    __tablename__ = "lessons"
    id = Column(Integer, primary_key=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False)
    name = Column(String(250))
    description = Column(Text, default="")
    order = Column(Integer, default=0)

    module = relationship("Module", back_populates="lessons")
    blocks = relationship("ContentBlock", back_populates="lesson", cascade="all, delete-orphan",
                          order_by="ContentBlock.order")


class ContentBlock(Base):
    __tablename__ = "content_blocks"
    id = Column(Integer, primary_key=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"), nullable=False)
    block_type = Column(String(20), default="text")  # video | text | file | image | quiz
    title = Column(String(250), default="")
    payload = Column(JSON, default=dict)  # url / html / questions etc.
    order = Column(Integer, default=0)

    lesson = relationship("Lesson", back_populates="blocks")


class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)


class ProgressRecord(Base):
    __tablename__ = "progress_records"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content_block_id = Column(Integer, ForeignKey("content_blocks.id"), nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "content_block_id"),)


# ---------------------------------------------------------------- Library (7.3/6.7)

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    name = Column(String(300))
    file_path = Column(String(600))
    mime = Column(String(150), default="")
    size = Column(Integer, default=0)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------- Investment (7.5)

class InvestmentCase(Base):
    __tablename__ = "investment_cases"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)
    company_name = Column(String(255), default="")
    type_id = Column(Integer, ForeignKey("business_types.id"))
    industry_id = Column(Integer, ForeignKey("business_industries.id"))
    tier_id = Column(Integer, ForeignKey("investment_tiers.id"))
    round_id = Column(Integer, ForeignKey("investment_rounds.id"))
    stage_id = Column(Integer, ForeignKey("investment_stages.id"))
    status_id = Column(Integer, ForeignKey("investment_statuses.id"))
    owner_id = Column(Integer, ForeignKey("users.id"))
    currency = Column(String(10), default="USD")
    amount_requested = Column(Float, default=0.0)
    investment_amount = Column(Float, default=0.0)
    co_financing_amount = Column(Float, default=0.0)
    collateral_description = Column(Text, default="")
    equity_offered_pct = Column(Float, default=0.0)
    sustainability_notes = Column(Text, default="")
    innovation_notes = Column(Text, default="")
    technical_assistance_request = Column(Text, default="")
    forex_rate = Column(Float, default=1.0)
    ceo_name = Column(String(220), default="")
    ceo_bio = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business")
    tier = relationship("InvestmentTier")
    round = relationship("InvestmentRound")
    stage = relationship("InvestmentStage")
    status = relationship("InvestmentStatus")
    timeline_entries = relationship("FinanceTimelineEntry", cascade="all, delete-orphan")
    payments = relationship("PaymentScheduleEntry", cascade="all, delete-orphan")


class FinanceTimelineEntry(Base):
    __tablename__ = "finance_timeline_entries"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("investment_cases.id"), nullable=False)
    entry_date = Column(Date)
    label = Column(String(250), default="")
    amount = Column(Float, default=0.0)
    direction = Column(String(10), default="in")  # in | out


class PaymentScheduleEntry(Base):
    __tablename__ = "payment_schedule_entries"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("investment_cases.id"), nullable=False)
    due_date = Column(Date)
    amount = Column(Float, default=0.0)
    paid = Column(Boolean, default=False)
    paid_date = Column(Date, nullable=True)


class CommitteeDecision(Base):
    __tablename__ = "committee_decisions"
    id = Column(Integer, primary_key=True)
    committee_level_id = Column(Integer, ForeignKey("committee_levels.id"), nullable=False)
    case_id = Column(Integer, ForeignKey("investment_cases.id"), nullable=False)
    decision = Column(String(30))  # approved | rejected | revision
    notes = Column(Text, default="")
    decided_by_id = Column(Integer, ForeignKey("users.id"))
    decided_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------- Collaboration (7.6)

class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    title = Column(String(300))
    body = Column(Text, default="")
    status_id = Column(Integer, ForeignKey("announcement_statuses.id"))
    published_at = Column(DateTime, default=datetime.utcnow)
    reactions_count = Column(Integer, default=0)

    status = relationship("AnnouncementStatus")


class AnnouncementReaction(Base):
    __tablename__ = "announcement_reactions"
    id = Column(Integer, primary_key=True)
    announcement_id = Column(Integer, ForeignKey("announcements.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reaction = Column(String(30), default="like")
    __table_args__ = (UniqueConstraint("announcement_id", "user_id"),)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    title = Column(String(300))
    description = Column(Text, default="")
    start = Column(DateTime)
    end = Column(DateTime, nullable=True)
    visibility = Column(String(20), default="public")  # public | private
    created_by_id = Column(Integer, ForeignKey("users.id"))


class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False)
    program_id = Column(Integer, ForeignKey("programs.id"), nullable=True)
    title = Column(String(250), default="")
    is_group = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    participants = relationship("ChatParticipant", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", cascade="all, delete-orphan", order_by="ChatMessage.sent_at")


class ChatParticipant(Base):
    __tablename__ = "chat_participants"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    last_read_at = Column(DateTime, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    body = Column(Text)
    sent_at = Column(DateTime, default=datetime.utcnow)

    sender = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(50), default="info")
    payload = Column(JSON, default=dict)
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
