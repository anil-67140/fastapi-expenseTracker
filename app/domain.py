from dataclasses import dataclass


@dataclass(frozen=True)
class DomainConfig:
    app_title: str
    app_subtitle: str
    item_label: str
    category_label: str
    status_label: str
    target_date_label: str
    category_options: tuple[str, ...]
    status_options: tuple[str, ...]
    empty_state_title: str
    empty_state_text: str


DOMAIN_CONFIG = DomainConfig(
    app_title="Expense Tracker",
    app_subtitle="Track daily spending, categories, and budget focus points.",
    item_label="Expense entry",
    category_label="Category",
    status_label="Payment status",
    target_date_label="Expense date",
    category_options=("food", "transport", "housing", "health", "education", "tools"),
    status_options=("planned", "paid", "reimbursed", "canceled"),
    empty_state_title="No expenses yet",
    empty_state_text="Add your first expense entry to start tracking money flow.",
)


def valid_category(value: str) -> bool:
    return value in DOMAIN_CONFIG.category_options


def valid_status(value: str) -> bool:
    return value in DOMAIN_CONFIG.status_options
