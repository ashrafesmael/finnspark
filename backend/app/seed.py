"""Seed finnspark with OCIF-style demo data (spec §2/§15.3)."""
import random
from datetime import datetime, timedelta

from app.database import Base, SessionLocal, engine
from app.models import (
    Applicant, ApplicantStatus, Announcement, AnnouncementReaction, AnnouncementStatus,
    ApplicationForm, ApplicationFormField, ApplicationFormFieldOption, Business, BusinessFounder,
    BusinessIndustry, BusinessType, CalendarEvent, Chat, ChatMessage, ChatParticipant, CommitteeLevel,
    ContentBlock, Course, CourseStatus, District, Enrollment, FieldType, FinanceTimelineEntry, FormStatus,
    Gender, InvestmentCase, InvestmentRound, InvestmentStage, InvestmentStatus, InvestmentTier,
    Lesson, MentorConclusionQuestion, MentorReviewQuestion, Mentorship, Module, Notification,
    Organization, OrganizationStatus, PaymentScheduleEntry, Program, ProgramStatus, ProgramType,
    ProgressRecord, Province, Role, ScoringForm, ScoringQuestion, SelectionStage, User, UserStatus,
    UserRole, Channel,
)

random.seed(42)


def ref(db, model, code_name):
    return db.query(model).filter(model.code_name == code_name).first()


def main():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # ------------------------------------------------------------ reference data
    org_status = OrganizationStatus(name="Active", code_name="active")
    user_active = UserStatus(name="Active", code_name="active")
    user_invited = UserStatus(name="Invited", code_name="invited")
    form_draft = FormStatus(name="Draft", code_name="draft")
    form_published = FormStatus(name="Published", code_name="published")
    course_published = CourseStatus(name="Published", code_name="published")
    program_status = ProgramStatus(name="Active", code_name="active")
    ann_published = AnnouncementStatus(name="Published", code_name="published")

    st_invited = ApplicantStatus(name="Invited", code_name="invited")
    st_in_selection = ApplicantStatus(name="In Selection", code_name="in_selection")
    st_rejected = ApplicantStatus(name="Rejected", code_name="rejected")
    st_archived = ApplicantStatus(name="Archived", code_name="archived")

    inv_in_approval = InvestmentStatus(name="In Approval", code_name="in_approval")
    inv_revision = InvestmentStatus(name="Revision", code_name="revision")
    inv_approved = InvestmentStatus(name="Approved", code_name="approved")
    inv_rejected = InvestmentStatus(name="Rejected", code_name="rejected")

    tier1 = InvestmentTier(name="Tier 1", code_name="tier_1")
    tier2 = InvestmentTier(name="Tier 2", code_name="tier_2")
    tier3 = InvestmentTier(name="Tier 3", code_name="tier_3")

    rounds = [InvestmentRound(name=n, code_name=c) for n, c in [
        ("Pre-seed", "pre_seed"), ("Seed", "seed"), ("Seed plus", "seed_plus"),
        ("Series A", "series_a"), ("Series B", "series_b"), ("Series C", "series_c"), ("IPO", "ipo")]]

    male = Gender(name="Male", code_name="male")
    female = Gender(name="Female", code_name="female")

    types = [BusinessType(name="Startup", code_name="startup"),
             BusinessType(name="Ideation Stage", code_name="ideation"),
             BusinessType(name="SGB", code_name="sgb")]

    industry_names = [
        "Accommodation, Food & Beverage Services", "Agroforestry", "Crops & Horticulture",
        "ECD & Education", "Electric, Auto, Equipment & Chemicals", "Entrepreneurship Skills",
        "Environmental Services & Management", "Fashion, Apparel & Crafts",
        "Financial, Professional & Management Services", "Healthcare & Allied Services",
        "ICT & Digital Services", "Livestock, Aquaculture & Apiculture",
        "Other Professional Services", "Processed Food",
        "Public Administration, Community & Social Services", "Soft & Employability Skills",
        "Transportation & Travel", "Wholesale & Retail"]
    industries = [BusinessIndustry(name=n, code_name=n.lower().replace(" ", "_")[:40])
                  for n in industry_names]

    field_types = [FieldType(name=n, code_name=c) for n, c in [
        ("Header", "header"), ("Input", "input"), ("Poll", "poll"), ("Multiply Poll", "multi_poll"),
        ("Spinner", "spinner"), ("File Upload", "file"), ("Date", "date"),
        ("Number", "number"), ("Long Text", "long_text"), ("Scoring Question", "scoring_form")]]

    db.add_all([org_status, user_active, user_invited, form_draft, form_published,
                course_published, program_status, ann_published,
                st_invited, st_in_selection, st_rejected, st_archived,
                inv_in_approval, inv_revision, inv_approved, inv_rejected,
                tier1, tier2, tier3, *rounds, male, female, *types, *industries, *field_types])
    db.flush()

    # ------------------------------------------------------------ geography
    from app.models import Country
    jordan_c = Country(name="Jordan", code_name="jo")
    lebanon_c = Country(name="Lebanon", code_name="lb")
    egypt_c = Country(name="Egypt", code_name="eg")
    palestine_c = Country(name="Palestine", code_name="ps")
    db.add_all([jordan_c, lebanon_c, egypt_c, palestine_c])
    db.flush()
    amman_prov = Province(country_id=jordan_c.id, name="Amman")
    irbid_prov = Province(country_id=jordan_c.id, name="Irbid")
    zarqa_prov = Province(country_id=jordan_c.id, name="Zarqa")
    aqaba_prov = Province(country_id=jordan_c.id, name="Aqaba")
    mount_leb = Province(country_id=lebanon_c.id, name="Mount Lebanon")
    cairo_gov = Province(country_id=egypt_c.id, name="Cairo")
    db.add_all([amman_prov, irbid_prov, zarqa_prov, aqaba_prov, mount_leb, cairo_gov])
    db.flush()
    districts = []
    for prov, names in (
            (amman_prov, ["Amman City", "Wadi Al-Seer", "Tla' Al-Ali", "Marka"]),
            (irbid_prov, ["Irbid City", "Ajloun"]),
            (zarqa_prov, ["Zarqa City", "Ruseifa"]),
            (aqaba_prov, ["Aqaba City"]),
            (mount_leb, ["Baabda", "Metn"]),
            (cairo_gov, ["Nasr City", "Maadi"])):
        for n in names:
            districts.append(District(province_id=prov.id, name=n))
    db.add_all(districts)
    geo = [(jordan_c.id, amman_prov.id, districts[0].id),
           (jordan_c.id, irbid_prov.id, districts[4].id),
           (jordan_c.id, zarqa_prov.id, districts[6].id),
           (jordan_c.id, aqaba_prov.id, districts[8].id),
           (lebanon_c.id, mount_leb.id, districts[9].id),
           (egypt_c.id, cairo_gov.id, districts[11].id)]
    db.flush()

    # ------------------------------------------------------------ tenancy
    org = Organization(name="Finnpact LTD", registration_date=datetime(2024, 3, 1).date(),
                       status_id=org_status.id)
    org2 = Organization(name="Mont Choisy Group", registration_date=datetime(2023, 1, 15).date(),
                        status_id=org_status.id)
    db.add_all([org, org2])
    db.flush()
    from app.models import Branch
    branch_jo = Branch(organization_id=org.id, name="Finnpact — Jordan")
    branch_mu = Branch(organization_id=org2.id, name="Mont Choisy — Mauritius")
    db.add_all([branch_jo, branch_mu])
    db.flush()

    def make_role(bid, name, code, constant=True, perms=None):
        r = Role(branch_id=bid, name=name, code_name=code, is_constant=constant,
                 permissions=perms or [])
        db.add(r)
        return r

    roles = {}
    for b in (branch_jo, branch_mu):
        for name, code, const in [("Administrator", "branch_admin", True),
                                  ("Organization Administrator", "organization_admin", True),
                                  ("Mentor", "mentor", True),
                                  ("Entrepreneur", "entrepreneur", True)]:
            roles[(b.id, code)] = make_role(b.id, name, code, const)
        roles[(b.id, "investment_manager")] = make_role(
            b.id, "Investment Manager", "investment_manager", False)

    def make_user(email, first, last, position, status=user_active, company="", phone=""):
        u = User(email=email, password_hash="", first_name=first, last_name=last,
                 position=position, status_id=status.id, company=company, phone=phone)
        return u

    from app.security import hash_password
    admin = make_user("admin@finnpact.jo", "Ashraf", "Esmael", "Branch Administrator")
    orgadmin = make_user("orgadmin@finnpact.jo", "Lina", "Haddad", "Organization Administrator")
    inv_mgr = make_user("investments@finnpact.jo", "Omar", "Khalil", "Investment Manager")
    mentors = [make_user(f"mentor{i}@finnpact.jo", n[0], n[1], "Mentor")
               for i, n in enumerate([
                   ("Sara", "Nasser"), ("Tarek", "Amoudi"), ("Dana", "Qasem"),
                   ("Yusuf", "Barakat"), ("Maya", "Saleh"), ("Karim", "Daher")])]
    entrepreneurs = [
        make_user(f"founder{i}@startup.jo", f"Founder{i}", "Test", "Entrepreneur",
                  company=f"Startup {i}", status=user_active)
        for i in range(1, 6)]
    all_users = [admin, orgadmin, inv_mgr, *mentors, *entrepreneurs]
    for u in all_users:
        u.password_hash = hash_password({
            "admin@finnpact.jo": "Admin123!",
            "orgadmin@finnpact.jo": "Admin123!",
            "investments@finnpact.jo": "Admin123!"}.get(u.email, "Demo123!"))
    db.add_all(all_users)
    db.flush()

    memberships = [
        (admin, branch_jo, "branch_admin"), (admin, branch_mu, "branch_admin"),
        (orgadmin, branch_jo, "organization_admin"), (inv_mgr, branch_jo, "investment_manager"),
    ] + [(m, branch_jo, "mentor") for m in mentors] \
      + [(e, branch_jo, "entrepreneur") for e in entrepreneurs]
    for u, b, code in memberships:
        db.add(UserRole(user_id=u.id, role_id=roles[(b.id, code)].id, branch_id=b.id))
    db.flush()

    # ------------------------------------------------------------ selection stages
    stage_names = ["Track I Onboarding", "Track I Support", "Pitch Stage",
                   "Track II Onboarding", "Track II Support"]
    stages = [SelectionStage(branch_id=branch_jo.id, name=n, order=i,
                             description=f"{n} selection stage")
              for i, n in enumerate(stage_names)]
    inv_stages = [InvestmentStage(branch_id=branch_jo.id, name=n, order=i)
                  for i, n in enumerate(["Application", "Evaluation", "Pitching", "Selection",
                                         "Approved"])]
    committees = [CommitteeLevel(branch_id=branch_jo.id, name="OCIF Track II Selection Committee – "
                                 "Cohort 3 – 2026", order=0),
                  CommitteeLevel(branch_id=branch_jo.id,
                                 name="OCIF Investment Committee – Final", order=1)]
    channel = Channel(branch_id=branch_jo.id, name="Direct Application")
    db.add_all([*stages, *inv_stages, *committees, channel])
    db.flush()

    # ------------------------------------------------------------ programs
    pt_track1 = ProgramType(branch_id=branch_jo.id, name="Track I Support – 6/8 Months",
                            duration_months=8)
    pt_track2 = ProgramType(branch_id=branch_jo.id, name="Track II Support – 12 Months",
                            duration_months=12)
    db.add_all([pt_track1, pt_track2])
    db.flush()
    prog1 = Program(branch_id=branch_jo.id, program_type_id=pt_track1.id,
                    name="OCIF Cohort 3 – Track I (2026)", status_id=program_status.id,
                    scoring_required=True, creation_date=datetime(2026, 1, 15))
    prog2 = Program(branch_id=branch_jo.id, program_type_id=pt_track2.id,
                    name="OCIF Cohort 2 – Track II (2026)", status_id=program_status.id,
                    scoring_required=True, creation_date=datetime(2025, 6, 1))
    db.add_all([prog1, prog2])
    db.flush()

    # ------------------------------------------------------------ application form
    app_form = ApplicationForm(
        branch_id=branch_jo.id, program_id=prog1.id, kind="application",
        name_i18n={"en": "OCIF Track I Application Form", "ar": "نموذج طلب المسار الأول"},
        main_language="en", status_id=form_published.id,
        form_description="Onboarding form for OCIF Track I Support applicants.")
    db.add(app_form)
    db.flush()

    def add_field(form, label_en, type_code, required=False, options=None):
        ft = ref(db, FieldType, type_code)
        fld = ApplicationFormField(application_form_id=form.id,
                                   name_i18n={"en": label_en},
                                   field_type_id=ft.id, is_required=required,
                                   order=len(form.fields))
        if options:
            for o in options:
                fld.options.append(ApplicationFormFieldOption(name_i18n={"en": o},
                                                              order=len(fld.options)))
        form.fields.append(fld)
        return fld

    add_field(app_form, "Section 1 — Founder details", "header")
    add_field(app_form, "First name", "input", True)
    add_field(app_form, "Last name", "input", True)
    add_field(app_form, "Email", "input", True)
    add_field(app_form, "Date of birth", "date")
    add_field(app_form, "Gender", "poll", False, ["Male", "Female"])
    add_field(app_form, "Identity Card or Passport (upload)", "file", True)
    add_field(app_form, "Section 2 — Business details", "header")
    add_field(app_form, "Business / Project name", "input", True)
    add_field(app_form, "Industry", "spinner", True,
              ["ICT & Digital Services", "Processed Food", "Fashion, Apparel & Crafts"])
    add_field(app_form, "Years of operation", "number")
    add_field(app_form, "What problem does your business solve?", "long_text", True)
    db.commit()

    scoring_form = ScoringForm(
        branch_id=branch_jo.id, program_id=prog1.id, selection_stage_id=stages[1].id,
        is_for_graduation=False, name_i18n={"en": "Track I Evaluation Scorecard"},
        status_id=form_published.id,
        form_description="Weighted evaluator scorecard for Track I applicants.")
    db.add(scoring_form)
    db.flush()
    weights = [("Market opportunity", 25), ("Team strength", 25), ("Product readiness", 20),
               ("Social impact", 20), ("Financial viability", 10)]
    total_w = sum(w for _, w in weights)
    for i, (name, w) in enumerate(weights):
        scoring_form.questions.append(ScoringQuestion(
            name=name, description=f"Rate {name.lower()} from 0 to 10.",
            weightage=100.0 * w / total_w, order=i))
    grad_form = ScoringForm(
        branch_id=branch_jo.id, program_id=prog1.id, is_for_graduation=True,
        name_i18n={"en": "Graduation Readiness Scorecard"}, status_id=form_published.id)
    db.add(grad_form)
    db.flush()
    for i, (name, w) in enumerate([("Course completion", 40), ("Mentor recommendation", 35),
                                   ("Final pitch quality", 25)]):
        grad_form.questions.append(ScoringQuestion(name=name, weightage=float(w), order=i))

    inv_form = ApplicationForm(
        branch_id=branch_jo.id, kind="investment",
        name_i18n={"en": "OCIF Track II Application Form"}, status_id=form_published.id,
        form_description="Application form for OCIF investment track.")
    db.add(inv_form)
    db.flush()
    add_field(inv_form, "Requested investment amount (USD)", "number", True)
    add_field(inv_form, "Use of funds", "long_text", True)
    add_field(inv_form, "Pitch deck", "file", True)
    db.commit()

    # ------------------------------------------------------------ applicants (80)
    first_names = ["Ahmad", "Rania", "Mohammad", "Fatima", "Omar", "Noor", "Ali", "Layla",
                   "Hassan", "Maryam", "Zaid", "Salma", "Khalid", "Hala", "Samir", "Dina"]
    last_names = ["Al-Zoubi", "Kanaan", "Odeh", "Malkawi", "Sukkar", "Nabulsi", "Tarawneh",
                  "Halabi", "Masri", "Shami"]
    biz_prefixes = ["Green", "Smart", "Sunrise", "Urban", "Golden", "Blue", "Nova", "Eco",
                    "Future", "Pioneer"]
    biz_suffixes = ["Farms", "Tech", "Foods", "Designs", "Logistics", "Health", "Academy",
                    "Energy", "Crafts", "Solutions"]

    applicants = []
    for i in range(80):
        gender = random.choice([male, female])
        country_idx = 0 if i < 60 else random.choice(range(len(geo)))
        c_id, p_id, d_id = geo[country_idx]
        age = random.randint(20, 55)
        applicant = Applicant(
            branch_id=branch_jo.id,
            program_id=random.choices([prog1.id, prog2.id], weights=[70, 30])[0],
            selection_stage_id=random.choices([s.id for s in stages],
                                              weights=[30, 30, 20, 10, 10])[0],
            email=f"applicant{i + 1}@example.com",
            first_name=random.choice(first_names),
            last_name=random.choice(last_names),
            business_name=f"{random.choice(biz_prefixes)}{random.choice(biz_suffixes)} {i + 1}",
            country_id=c_id, province_id=p_id, district_id=d_id,
            industry_id=random.choice(industries).id,
            gender_id=gender.id, age=age,
            channel_id=channel.id,
            average_score=round(random.uniform(35, 95), 1) if i % 3 else None,
            registered=i < 12,
            application_date=datetime(2026, random.choice([1, 2, 3]), random.randint(1, 28)),
        )
        applicant.status_id = random.choices(
            [st_invited.id, st_in_selection.id, st_rejected.id, st_archived.id],
            weights=[45, 40, 10, 5])[0]
        answers = {
            "field_first_name": applicant.first_name, "field_last_name": applicant.last_name,
            "field_email": applicant.email,
            "field_business": applicant.business_name,
            "age": age,
        }
        applicant.answers = answers
        applicants.append(applicant)
    db.add_all(applicants)
    db.commit()

    # ------------------------------------------------------------ businesses (79 selected)
    businesses = []
    selected_applicants = applicants[:79]
    for i, ap in enumerate(selected_applicants):
        b = Business(
            branch_id=branch_jo.id, program_id=ap.program_id, applicant_id=ap.id,
            name=ap.business_name,
            type_id=random.choice(types).id, industry_id=ap.industry_id,
            graduation_status="Graduated" if i < 4 and ap.program_id == prog2.id else "Not graduated",
            course_progress=round(random.uniform(0, 100), 1),
            course_score=round(random.uniform(40, 98), 1),
            average_evaluator_score=ap.average_score or round(random.uniform(50, 90), 1),
            created_at=ap.application_date + timedelta(days=random.randint(5, 40)),
        )
        b.founders.append(BusinessFounder(
            first_name=ap.first_name, last_name=ap.last_name, email=ap.email,
            gender_id=ap.gender_id, age=ap.age, position="CEO"))
        businesses.append(b)
    db.add_all(businesses)
    db.commit()

    for b in businesses[:30]:
        for m in random.sample(mentors, k=random.randint(1, 2)):
            db.add(Mentorship(business_id=b.id, mentor_id=m.id))
    db.commit()

    review_qs = ["How would you rate the founder's commitment over the review period?",
                 "What progress was made on the action points from the last session?",
                 "Which key risks do you see for the next quarter?",
                 "Score the team's ability to execute on the business plan."]
    concl_qs = ["Overall, do you recommend this business for graduation?",
                "Summarise the business's growth during the programme."]
    for q_text, o in enumerate(review_qs):
        db.add(MentorReviewQuestion(program_id=prog1.id, text=q_text, order=o))
    for q_text, o in enumerate(concl_qs):
        db.add(MentorConclusionQuestion(program_id=prog2.id, text=q_text, order=o))

    # ------------------------------------------------------------ courses (12)
    course_titles = [
        "Entrepreneurship Fundamentals", "Financial Literacy for Founders", "Digital Marketing",
        "Operations & Supply Chain", "Leadership & Team Building", "Sales Pipeline Mastery",
        "Product Development Sprint", "Impact Measurement", "Legal & Compliance Basics",
        "Fundraising Essentials", "Business Planning Guide", "Customer Discovery Lab"]
    courses = []
    for idx, title in enumerate(course_titles):
        lang = random.choice(["en", "en", "en", "ar"])
        c = Course(
            branch_id=branch_jo.id, program_id=prog1.id if idx < 8 else None,
            name=title, language=lang,
            subtitle_languages=random.sample(["en", "ru", "ar"], k=random.randint(1, 2)),
            description=f"Practical training course: {title}.",
            status_id=course_published.id,
            created_at=datetime(2026, 1, 20) + timedelta(days=idx * 7))
        module_names = [f"Module 1: Core concepts", "Module 2: Applied practice"]
        for mi, mod_name in enumerate(module_names):
            module = Module(course_id=c.id, name=mod_name, order=mi,
                            description=f"{mod_name} of {title}")
            for li, lesson_name in enumerate(["Session A", "Session B"]):
                lesson = Lesson(module_id=module.id, name=f"{lesson_name} — {title}",
                                order=li, description="")
                lesson.blocks.append(ContentBlock(
                    block_type="video", title=f"Video: {lesson_name}",
                    payload={"url": "https://www.w3schools.com/html/mov_bbb.mp4"},
                    order=0))
                lesson.blocks.append(ContentBlock(
                    block_type="text", title="Key takeaways",
                    payload={"html": "<p>Read the summary notes for this lesson.</p>"}, order=1))
                module.lessons.append(lesson)
            c.modules.append(module)
        courses.append(c)
    db.add_all(courses)
    db.commit()

    # enroll entrepreneurs + some progress
    for e in entrepreneurs:
        for c in random.sample(courses, k=3):
            db.add(Enrollment(user_id=e.id, course_id=c.id, started_at=datetime.utcnow()))

    # ------------------------------------------------------------ announcements / calendar
    anns = []
    for i, (title, body) in enumerate([
        ("Welcome to OCIF Cohort 3!", "Kick-off session on 5 February at 10:00 AM Amman time."),
        ("Pitch training workshop", "Optional pitch practice sessions every Thursday."),
        ("Mentor matching completed", "You can now see your assigned mentor in your profile."),
        ("Demo Day — save the date", "Demo Day will be held at the end of Track II.")]):
        a = Announcement(branch_id=branch_jo.id, program_id=[prog1.id, prog2.id, None, None][i],
                         title=title, body=body, status_id=ann_published.id,
                         published_at=datetime(2026, 2, 1) + timedelta(days=i * 9),
                         reactions_count=0)
        anns.append(a)
    db.add_all(anns)
    db.commit()
    for a in anns:
        for u in entrepreneurs[:3]:
            db.add(AnnouncementReaction(announcement_id=a.id, user_id=u.id))
            a.reactions_count += 1

    events = [
        ("OCIF Kick-off", datetime(2026, 2, 5, 10, 0), datetime(2026, 2, 5, 12, 0), "public"),
        ("Mentor–founder sync week", datetime(2026, 3, 9, 9, 0), datetime(2026, 3, 13, 17, 0), "public"),
        ("Investment committee — internal", datetime(2026, 4, 14, 15, 0),
         datetime(2026, 4, 14, 16, 30), "private"),
        ("Demo Day rehearsal", datetime(2026, 5, 20, 14, 0), datetime(2026, 5, 20, 17, 0), "public"),
    ]
    for title, start, end, vis in events:
        db.add(CalendarEvent(branch_id=branch_jo.id, title=title, start=start, end=end,
                             visibility=vis, created_by_id=admin.id))

    chat = Chat(branch_id=branch_jo.id, program_id=prog1.id, is_group=True,
                title="OCIF Cohort 3 — General")
    db.add(chat)
    db.flush()
    for u in [admin, inv_mgr, *mentors[:2], *entrepreneurs[:3]]:
        db.add(ChatParticipant(chat_id=chat.id, user_id=u.id))
    msgs = [("Welcome everyone to the cohort chat!", admin.id),
            ("Thanks! Excited to get started.", entrepreneurs[0].id),
            ("Reminder: office hours every Wednesday.", mentors[0].id)]
    for body, uid in msgs:
        db.add(ChatMessage(chat_id=chat.id, sender_id=uid, body=body))
    dm = Chat(branch_id=branch_jo.id, is_group=False, title="")
    db.add(dm)
    db.flush()
    db.add(ChatParticipant(chat_id=dm.id, user_id=admin.id))
    db.add(ChatParticipant(chat_id=dm.id, user_id=inv_mgr.id))
    db.add(ChatMessage(chat_id=dm.id, sender_id=admin.id, body="Can you review case #1 today?"))
    db.commit()

    for uid in [inv_mgr.id, entrepreneurs[0].id]:
        db.add(Notification(user_id=uid, type="info",
                            payload={"message": "New announcement: Welcome to OCIF Cohort 3!"}))

    # ------------------------------------------------------------ investment cases
    cases = []
    portfolio_targets = businesses[:10]
    for i, b in enumerate(portfolio_targets):
        stage = inv_stages[min(i // 2, len(inv_stages) - 1)]
        if i < 6:
            status = inv_approved
        elif i == 6:
            status = inv_revision
        elif i == 7:
            status = inv_rejected
        else:
            status = inv_in_approval
        amount = float(random.choice([15000, 25000, 40000, 60000, 80000]))
        case = InvestmentCase(
            branch_id=branch_jo.id, business_id=b.id, company_name=b.name,
            type_id=b.type_id, industry_id=b.industry_id,
            tier_id=random.choice([tier1, tier2, tier3]).id,
            round_id=random.choice(rounds[:4]).id,
            stage_id=stage.id, status_id=status.id, owner_id=inv_mgr.id,
            currency=random.choice(["USD", "USD", "JOD"]), forex_rate=0.71,
            amount_requested=amount, investment_amount=amount if status == inv_approved else 0.0,
            co_financing_amount=round(amount * 0.2, 2) if status == inv_approved else 0.0,
            equity_offered_pct=float(random.choice([5, 7, 10, 12])),
            collateral_description="Personal guarantee + equipment lien." if i % 2 else "",
            sustainability_notes="Strong environmental impact plan." if i % 3 == 0 else "",
            innovation_notes="Proprietary process technology." if i % 4 == 0 else "",
            technical_assistance_request="Bookkeeping support for 6 months." if i % 2 else "",
            ceo_name=(f"{b.founders[0].first_name} {b.founders[0].last_name}"
                      if b.founders else ""),
            created_at=datetime(2026, 3, 1) + timedelta(days=i * 11))
        cases.append(case)
    db.add_all(cases)
    db.commit()
    from datetime import date as date_cls
    for c in cases:
        if c.status_id == inv_approved.id:
            for m in range(1, 5):
                month = min(12, 4 + m * 2)
                db.add(PaymentScheduleEntry(
                    case_id=c.id, due_date=date_cls(2026, month, 1),
                    amount=round((c.investment_amount or 0) / 4, 2), paid=m <= 2,
                    paid_date=date_cls(2026, month, 3) if m <= 2 else None))
            db.add(FinanceTimelineEntry(case_id=c.id, entry_date=date_cls(2026, 4, 1),
                                        label="Disbursement 1", amount=c.investment_amount / 2,
                                        direction="out"))
            db.add(FinanceTimelineEntry(case_id=c.id, entry_date=date_cls(2026, 7, 1),
                                        label="Revenue milestone", amount=5000, direction="in"))

    db.commit()
    counts = {
        "applicants": db.query(Applicant).count(),
        "businesses": db.query(Business).count(),
        "courses": db.query(Course).count(),
        "cases": db.query(InvestmentCase).count(),
        "users": db.query(User).count(),
    }
    print("Seed complete:", counts)
    print("Login: admin@finnpact.jo / Admin123!")
    db.close()


if __name__ == "__main__":
    main()
