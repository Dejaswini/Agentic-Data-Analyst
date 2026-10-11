"""Unit tests for the read-only SQL validator (no database needed)."""
from datetime import date

from app.sql_validator import validate_sql

SCHEMA = {
    "regions": ["region_id", "region_name", "state"],
    "customers": ["customer_id", "customer_name", "city", "segment", "region_id"],
    "products": ["product_id", "product_name", "category", "unit_price"],
    "sales_representatives": ["rep_id", "rep_name", "region_id"],
    "sales": ["sale_id", "sale_date", "customer_id", "product_id", "rep_id",
              "quantity", "unit_price", "total_amount"],
}


def ok(sql):
    return validate_sql(sql, SCHEMA).ok


def errors(sql):
    return validate_sql(sql, SCHEMA).errors


def test_simple_select_allowed():
    assert ok("SELECT product_name, unit_price FROM products ORDER BY unit_price DESC LIMIT 5")


def test_select_with_joins_and_aggregation_allowed():
    sql = """
        SELECT p.product_name, SUM(s.total_amount) AS revenue
        FROM sales s
        JOIN products p ON p.product_id = s.product_id
        JOIN customers c ON c.customer_id = s.customer_id
        JOIN regions r ON r.region_id = c.region_id
        WHERE r.state = 'Tamil Nadu' AND s.sale_date >= DATE '2025-01-01'
        GROUP BY p.product_name
        ORDER BY revenue DESC
    """
    assert ok(sql)


def test_with_select_allowed():
    assert ok("WITH t AS (SELECT rep_id, SUM(quantity) AS q FROM sales GROUP BY rep_id) "
              "SELECT * FROM t ORDER BY q DESC")


def test_drop_blocked():
    assert not ok("DROP TABLE sales")


def test_delete_blocked():
    assert not ok("DELETE FROM sales WHERE sale_id = 1")


def test_update_blocked():
    assert not ok("UPDATE sales SET quantity = 0")


def test_insert_blocked():
    assert not ok("INSERT INTO regions (region_name, state) VALUES ('X', 'Y')")


def test_multiple_statements_blocked():
    assert not ok("SELECT 1; DROP TABLE sales")


def test_select_into_blocked():
    assert not ok("SELECT * INTO backup FROM sales")


def test_alter_blocked():
    assert not ok("ALTER TABLE sales ADD COLUMN note text")


def test_unknown_table_rejected():
    assert any("Unknown table" in e for e in errors("SELECT * FROM secret_table"))


def test_unknown_qualified_column_rejected():
    assert any("Unknown column" in e
               for e in errors("SELECT products.no_such_col FROM products"))


def test_unknown_unqualified_column_rejected():
    assert any("Unknown column" in e
               for e in errors("SELECT no_such_col FROM products"))


def test_unparseable_rejected():
    assert not ok("SELEC nonsense FROM")


def test_forbidden_function_blocked():
    assert not ok("SELECT pg_read_file('/etc/passwd')")


def test_alias_column_resolves():
    sql = ("SELECT p.product_name, SUM(s.total_amount) AS total "
           "FROM sales s JOIN products p ON p.product_id = s.product_id "
           "GROUP BY p.product_name")
    assert ok(sql)
