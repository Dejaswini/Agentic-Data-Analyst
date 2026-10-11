"""Unit tests for chart selection logic (no LLM, no DB)."""
from datetime import date

from app.charts import choose_chart, override_from_question


def test_trend_question_with_date_column_gives_line():
    spec = choose_chart(
        "Show me the monthly sales trend",
        ["month", "total_sales"],
        [[date(2025, 1, 1), 120000], [date(2025, 2, 1), 135000]],
    )
    assert spec.type == "line"
    assert spec.x == "month" and spec.y == "total_sales"


def test_comparison_question_gives_bar():
    spec = choose_chart(
        "Compare sales between Tamil Nadu and Kerala",
        ["state", "total_sales"],
        [["Tamil Nadu", 500000], ["Kerala", 320000]],
    )
    assert spec.type == "bar"


def test_top_n_question_gives_bar():
    spec = choose_chart(
        "Which product generated the highest revenue?",
        ["product_name", "revenue"],
        [["Mixer Grinder 750W", 90000], ["Ceiling Fan 1200mm", 80000]],
    )
    assert spec.type == "bar"


def test_share_question_gives_pie():
    spec = choose_chart(
        "What is the share of each category in total sales?",
        ["category", "total_sales"],
        [["Grocery", 400000], ["Electronics", 300000]],
    )
    assert spec.type == "pie"


def test_relationship_gives_scatter():
    spec = choose_chart(
        "Is there a relationship between quantity and unit price?",
        ["quantity", "unit_price"],
        [[3, 420], [5, 165]],
    )
    assert spec.type == "scatter"


def test_user_override_wins():
    spec = choose_chart(
        "Compare regions but show it as a pie chart",
        ["region_name", "total_sales"],
        [["Chennai Metro", 100], ["Kochi", 80]],
    )
    assert spec.type == "pie"


def test_override_phrase_detected():
    assert override_from_question("show it as a line chart") == "line"
    assert override_from_question("as a bar graph please") == "bar"
    assert override_from_question("give me a donut") == "pie"
    assert override_from_question("just the table") == "table"
    assert override_from_question("what were total sales") is None


def test_date_shape_without_keywords_falls_back_to_line():
    spec = choose_chart(
        "Sales by month",
        ["month", "amt"],
        [[date(2025, 3, 1), 10], [date(2025, 4, 1), 20]],
    )
    assert spec.type == "line"


def test_no_numeric_column_gives_table():
    spec = choose_chart("List customers", ["customer_name"], [["Anand Stores"]])
    assert spec.type == "table"


def test_empty_result_gives_table():
    spec = choose_chart("Total sales", ["total"], [])
    assert spec.type == "table"
