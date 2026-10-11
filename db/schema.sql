-- Agentic Data Analyst - demo sales schema (PostgreSQL)

DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS sales_representatives;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS regions;

CREATE TABLE regions (
    region_id   SERIAL PRIMARY KEY,
    region_name TEXT NOT NULL,
    state       TEXT NOT NULL
);

CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    customer_name TEXT NOT NULL,
    city          TEXT NOT NULL,
    segment       TEXT NOT NULL CHECK (segment IN ('Retail', 'Wholesale', 'Corporate')),
    region_id     INT NOT NULL REFERENCES regions(region_id)
);

CREATE TABLE products (
    product_id   SERIAL PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT NOT NULL,
    unit_price   NUMERIC(10, 2) NOT NULL CHECK (unit_price > 0)
);

CREATE TABLE sales_representatives (
    rep_id     SERIAL PRIMARY KEY,
    rep_name   TEXT NOT NULL,
    region_id  INT NOT NULL REFERENCES regions(region_id)
);

CREATE TABLE sales (
    sale_id       SERIAL PRIMARY KEY,
    sale_date     DATE NOT NULL,
    customer_id   INT NOT NULL REFERENCES customers(customer_id),
    product_id    INT NOT NULL REFERENCES products(product_id),
    rep_id        INT NOT NULL REFERENCES sales_representatives(rep_id),
    quantity      INT NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10, 2) NOT NULL,
    total_amount  NUMERIC(12, 2) NOT NULL
);

CREATE INDEX idx_sales_date ON sales (sale_date);
CREATE INDEX idx_sales_customer ON sales (customer_id);
CREATE INDEX idx_sales_product ON sales (product_id);
CREATE INDEX idx_sales_rep ON sales (rep_id);
