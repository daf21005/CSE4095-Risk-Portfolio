-- note: you can upload this file into Google Cloud then after run:
-- source 01_create_tables.sql;


-- Assume the database team_risk is created

-- parent tables, strategy must exist before transactions and holdings

CREATE TABLE IF NOT EXISTS strategy (
    Strategy_name VARCHAR(50) NOT NULL,
    Strategy_desc VARCHAR(50),
    Strategy_formula VARCHAR(255),
    PRIMARY KEY (Strategy_name)
);

CREATE TABLE IF NOT EXISTS company (
    Ticker VARCHAR(20),
    Comp_Name VARCHAR(50),
    Comp_Street VARCHAR(50),
    Comp_City VARCHAR(50),
    Comp_State VARCHAR(25),
    Comp_Zip VARCHAR(20),
    Comp_Country VARCHAR(20),
    Sector VARCHAR(50),
    Industry VARCHAR(50),
    PRIMARY KEY (Ticker)
);

CREATE TABLE IF NOT EXISTS sector (
  sec_name VARCHAR(50) NOT NULL,
  sec_desc VARCHAR(100),
  sec_percent DECIMAL(10,2),
  PRIMARY KEY (sec_name)
);

CREATE TABLE IF NOT EXISTS security (
  figi VARCHAR(255) NOT NULL,
  name VARCHAR(255),
  ticker VARCHAR(20),
  exchCode VARCHAR(10),
  securityType VARCHAR(25),
  marketSector VARCHAR(50),
  shareClassFIGI VARCHAR(20),
  securityType2 VARCHAR(20),
  securityDescription VARCHAR(30),
  PRIMARY KEY (figi)
);

-- market data

CREATE TABLE IF NOT EXISTS daily_price (
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open DECIMAL(19, 4),
    high DECIMAL(19, 4),
    low DECIMAL(19, 4),
    close DECIMAL(19, 4),
    volume BIGINT,
    adj_close DECIMAL(19, 4),
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    ticker	varchar(10) NOT NULL,
    date DATE NOT NULL,
    target_high_price decimal(19,4),
    target_low_price decimal(19,4),
    target_mean_price decimal(19,4),
    target_median_price	decimal(19,4),
    current_price decimal(19,4),
    recommendation_key varchar(50),
    recommendation_mean decimal(10,4),
    number_of_analyst_opinions int,
    trailing_pe decimal(10,4),
    forward_pe decimal(10,4),
    price_to_book decimal(10,4),
    peg_ratio decimal(10,4),
    ebitda decimal(24,4),
    revenue_growth decimal(10,4),
    return_on_equity decimal(10,4),
    fifty_two_week_high	decimal(19,4),
    fifty_two_week_low decimal(19,4),
    fifty_day_average decimal(19,4),
    two_hundred_day_average	decimal(19,4),
    beta decimal(10,4),
    PRIMARY KEY (ticker, date)
);

-- trading records (child tables of strategy)

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INT NOT NULL AUTO_INCREMENT,
    strategy VARCHAR(50),
    ticker VARCHAR(10),
    transaction_date DATE,
    transaction_type ENUM('BUY', 'SELL'),
    quantity DECIMAL(19, 4),
    price_per_share DECIMAL(19, 4),
    PRIMARY KEY (transaction_id)
);

CREATE TABLE IF NOT EXISTS holdings (
    Holding_strategy VARCHAR(50) NOT NULL,
    Holdings_date DATE NOT NULL,
    Holdings_ticker VARCHAR(20) NOT NULL,
    purchase_price DECIMAL(12, 2),
    holdings_amount INT,
    purchase_date DATE,
    purchase_cost DECIMAL(19, 4),
    PRIMARY KEY (Holding_strategy, Holding_date, Holding_ticker)
);