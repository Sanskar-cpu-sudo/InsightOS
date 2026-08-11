"""
seed_data.py
------------
Fills PostgreSQL with realistic, simulated business data so we have
something for the agents to actually analyze.

IMPORTANT DESIGN CHOICE:
We don't just generate random noise. We deliberately bake in ONE clear
story, matching the exact scenario from the project spec:

    Day -30 to Day -2  -> normal, stable business
    Day -1              -> a deployment happens (v2.1.4)
    Day 0 (today)       -> revenue drops, tickets spike, reviews turn negative,
                            and the ticket/review TEXT explicitly mentions slowness

This gives the Data Agent something real to flag, the Knowledge Agent
something real to retrieve, and the Decision Agent a genuine root cause
to reason its way to -- instead of us having to fake the reasoning later.
Run this with:
    python -m app.seed_data
"""

import random
from datetime import date, datetime, timedelta, UTC

from app.database import SessionLocal, init_db
from app.models import Sale, SupportTicket, Review, DeploymentLog

DEFAULT_COMPANY_ID = 1

# Realistic "normal" support ticket text (before the incident)
NORMAL_TICKET_TEMPLATES = [
    "How do I update my billing address?",
    "Can I get an invoice for last month's payment?",
    "I'd like to change my subscription plan.",
    "How do I reset my password?",
    "Is there a mobile app available?",
    "Can I export my data to CSV?",
    "How do I add a teammate to my workspace?",
    "What's included in the enterprise plan?",
]

# Ticket text AFTER the deployment incident -- explicitly about slowness/timeouts
INCIDENT_TICKET_TEMPLATES = [
    "The website becomes very slow after checkout, sometimes it just hangs.",
    "Checkout keeps timing out, I've tried three times now.",
    "Everything has been really laggy since yesterday, especially at checkout.",
    "Getting constant timeout errors when trying to complete my order.",
    "The app has been extremely slow for the past day, is something wrong?",
    "Checkout page freezes and never loads the confirmation.",
    "Support, please help -- payment page is stuck loading for minutes.",
    "My payment failed twice, the page just spins forever after I click pay.",
    "Is the site down? Checkout hasn't worked properly since yesterday.",
    "Placed an order but it's stuck on 'processing' for over 10 minutes.",
    "The checkout button doesn't respond half the time now.",
    "Getting a 'gateway timeout' error every time I try to pay.",
    "This is the third time today checkout has failed on me.",
    "Cart looks fine but payment step just loads endlessly.",
    "App crashed twice while I was trying to check out.",
    "Something changed recently -- checkout used to be instant, now it takes forever.",
    "Order confirmation email never arrived, payment page also froze.",
    "Very frustrating, tried checking out on mobile and desktop, both slow.",
]

# Deliberately kept small and reused - these are ROUTINE, ordinary
# questions unrelated to the incident, so some repetition here is fine
# and even realistic (most support tickets on a normal day are mundane).

NORMAL_REVIEW_TEMPLATES = [
    ("Great product, does exactly what we need.", 5),
    ("Solid tool, support team is responsive.", 4),
    ("Works well for our team, minor UI quirks.", 4),
    ("Really happy with the onboarding experience.", 5),
    ("Good value for the price.", 4),
]

INCIDENT_REVIEW_TEMPLATES = [
    ("Used to be great but it's been painfully slow lately.", 2),
    ("Checkout is broken, tried multiple times and it just hangs.", 1),
    ("Performance has really dropped in the last day or two.", 2),
    ("Frustrating experience -- pages time out constantly now.", 1),
    ("Was about to buy but the slow checkout made me give up.", 2),
    ("Payment page just spins and spins, never completes.", 1),
    ("Something broke recently, the whole site feels sluggish now.", 2),
    ("Tried to order three times, gave up because checkout kept failing.", 1),
    ("Not happy - app freezes right when I try to pay.", 2),
    ("Great product but the recent slowness is a dealbreaker.", 3),
]


def clear_existing_data(db):
    """Wipes previous simulated data so re-running seed_data.py is repeatable."""
    db.query(Sale).filter(Sale.company_id == DEFAULT_COMPANY_ID).delete()
    db.query(SupportTicket).filter(SupportTicket.company_id == DEFAULT_COMPANY_ID).delete()
    db.query(Review).filter(Review.company_id == DEFAULT_COMPANY_ID).delete()
    db.query(DeploymentLog).filter(DeploymentLog.company_id == DEFAULT_COMPANY_ID).delete()
    db.commit()


def seed_sales(db, days: int = 35):
    """
    Generates `days` of daily sales, ending TODAY.
    Last 2 days show a clear revenue/orders drop -- this is what the
    Data Agent's anomaly detection should catch.
    """
    today = date.today()
    base_revenue = 50000
    base_orders = 330

    for i in range(days, -1, -1):
        day = today - timedelta(days=i)
        is_incident_day = i <= 1  # today and yesterday show the drop

        if is_incident_day:
            revenue = base_revenue * random.uniform(0.60, 0.72)   # ~30-40% drop
            orders = int(base_orders * random.uniform(0.55, 0.68))
        else:
            revenue = base_revenue + random.uniform(-2000, 2000)
            orders = base_orders + random.randint(-15, 15)

        avg_order_value = round(revenue / max(orders, 1), 2)

        db.add(Sale(
            company_id=DEFAULT_COMPANY_ID,
            date=day,
            revenue=round(revenue, 2),
            orders=orders,
            avg_order_value=avg_order_value,
        ))
    db.commit()


def seed_support_tickets(db, normal_days: int = 20, incident_tickets: int = 18):
    """
    Normal days -> 1-3 routine tickets/day.
    Last day -> a spike of tickets, mostly about slowness/timeouts.
    """
    now = datetime.now(UTC)

    # Routine tickets spread across the past few weeks
    for i in range(normal_days, 1, -1):
        day = now - timedelta(days=i)
        for _ in range(random.randint(1, 3)):
            db.add(SupportTicket(
                company_id=DEFAULT_COMPANY_ID,
                created_at=day - timedelta(hours=random.randint(0, 23)),
                content=random.choice(NORMAL_TICKET_TEMPLATES),
                category="general",
            ))

    # Spike of incident-related tickets in the last ~18 hours.
    # We sample WITHOUT repetition first (so we don't get the same
    # sentence multiple times), and only reuse templates if we need
    # more tickets than we have unique templates for.
    chosen_texts = []
    pool = INCIDENT_TICKET_TEMPLATES.copy()
    random.shuffle(pool)
    while len(chosen_texts) < incident_tickets:
        if not pool:
            pool = INCIDENT_TICKET_TEMPLATES.copy()
            random.shuffle(pool)
        chosen_texts.append(pool.pop())

    for text in chosen_texts:
        db.add(SupportTicket(
            company_id=DEFAULT_COMPANY_ID,
            created_at=now - timedelta(hours=random.uniform(0, 18)),
            content=text,
            category="performance",
        ))

    db.commit()


def seed_reviews(db, normal_days: int = 20, incident_reviews: int = 8):
    """Same idea as tickets -- normal chatter, then a burst of negative reviews."""
    now = datetime.now(UTC)

    for i in range(normal_days, 1, -1):
        day = now - timedelta(days=i)
        if random.random() < 0.4:  # not every day has a review
            content, rating = random.choice(NORMAL_REVIEW_TEMPLATES)
            db.add(Review(
                company_id=DEFAULT_COMPANY_ID,
                created_at=day - timedelta(hours=random.randint(0, 23)),
                content=content,
                rating=rating,
            ))

    chosen_reviews = []
    pool = INCIDENT_REVIEW_TEMPLATES.copy()
    random.shuffle(pool)
    while len(chosen_reviews) < incident_reviews:
        if not pool:
            pool = INCIDENT_REVIEW_TEMPLATES.copy()
            random.shuffle(pool)
        chosen_reviews.append(pool.pop())

    for content, rating in chosen_reviews:
        db.add(Review(
            company_id=DEFAULT_COMPANY_ID,
            created_at=now - timedelta(hours=random.uniform(0, 20)),
            content=content,
            rating=rating,
        ))

    db.commit()


def seed_deployment_log(db):
    """
    One deployment, ~1.5 days ago -- right before the incident window starts.
    This is the 'smoking gun' the Knowledge Agent should surface and the
    Decision Agent should connect to the sales/ticket anomaly.
    """
    now = datetime.now(UTC)
    db.add(DeploymentLog(
        company_id=DEFAULT_COMPANY_ID,
        deployed_at=now - timedelta(hours=36),
        version="v2.1.4",
        description=(
            "Deployed v2.1.4: refactored checkout payment gateway integration "
            "and updated API request handling middleware."
        ),
    ))
    db.commit()


def run():
    print("Initializing database tables (if not already created)...")
    init_db()

    db = SessionLocal()
    try:
        print("Clearing old simulated data...")
        clear_existing_data(db)

        print("Seeding sales data (35 days, with a drop in the last 2 days)...")
        seed_sales(db)

        print("Seeding support tickets (routine + incident spike)...")
        seed_support_tickets(db)

        print("Seeding reviews (routine + incident spike)...")
        seed_reviews(db)

        print("Seeding one deployment log entry (the likely root cause)...")
        seed_deployment_log(db)

        print("Done. Database now contains a realistic incident scenario.")
    finally:
        db.close()


if __name__ == "__main__":
    run()