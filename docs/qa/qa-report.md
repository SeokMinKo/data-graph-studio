# DGS QA Report — 2026-02-23

## Summary
- Scenarios run: 66
- Pass: 65  Warn: 0  Fail: 1

## Results

| Dataset | Scenario | Status | Notes |
|---------|----------|--------|-------|
| 01_sales_simple.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '5b90e3f1'} |
| 01_sales_simple.csv | filter | ✅ pass | {'status': 'ok', 'column': 'date', 'op': 'eq', 'value': ''} |
| 01_sales_simple.csv | chart_bar | ✅ pass | True |
| 01_sales_simple.csv | chart_line | ✅ pass | True |
| 01_sales_simple.csv | chart_scatter | ✅ pass | True |
| 01_sales_simple.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 02_stock_ohlc.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '8ba0b4be'} |
| 02_stock_ohlc.csv | filter | ✅ pass | {'status': 'ok', 'column': 'date', 'op': 'eq', 'value': ''} |
| 02_stock_ohlc.csv | chart_bar | ✅ pass | True |
| 02_stock_ohlc.csv | chart_line | ✅ pass | True |
| 02_stock_ohlc.csv | chart_scatter | ✅ pass | True |
| 02_stock_ohlc.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 03_sensors_timeseries.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '25093e47'} |
| 03_sensors_timeseries.csv | filter | ✅ pass | {'status': 'ok', 'column': 'timestamp', 'op': 'eq', 'value': ''} |
| 03_sensors_timeseries.csv | chart_bar | ✅ pass | True |
| 03_sensors_timeseries.csv | chart_line | ✅ pass | True |
| 03_sensors_timeseries.csv | chart_scatter | ✅ pass | True |
| 03_sensors_timeseries.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 04_employees.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '9f8064a9'} |
| 04_employees.csv | filter | ✅ pass | {'status': 'ok', 'column': 'name', 'op': 'eq', 'value': ''} |
| 04_employees.csv | chart_bar | ✅ pass | True |
| 04_employees.csv | chart_line | ✅ pass | True |
| 04_employees.csv | chart_scatter | ✅ pass | True |
| 04_employees.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 05_products_inventory.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '23cda59f'} |
| 05_products_inventory.csv | filter | ✅ pass | {'status': 'ok', 'column': 'sku', 'op': 'eq', 'value': ''} |
| 05_products_inventory.csv | chart_bar | ✅ pass | True |
| 05_products_inventory.csv | chart_line | ✅ pass | True |
| 05_products_inventory.csv | chart_scatter | ✅ pass | True |
| 05_products_inventory.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 06_website_analytics.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': 'f78e8ab2'} |
| 06_website_analytics.csv | filter | ✅ pass | {'status': 'ok', 'column': 'date', 'op': 'eq', 'value': ''} |
| 06_website_analytics.csv | chart_bar | ✅ pass | True |
| 06_website_analytics.csv | chart_line | ✅ pass | True |
| 06_website_analytics.csv | chart_scatter | ✅ pass | True |
| 06_website_analytics.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 07_survey_results.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '9b26b8bc'} |
| 07_survey_results.csv | filter | ✅ pass | {'status': 'ok', 'column': 'respondent_id', 'op': 'eq', 'value': ''} |
| 07_survey_results.csv | chart_bar | ✅ pass | True |
| 07_survey_results.csv | chart_line | ✅ pass | True |
| 07_survey_results.csv | chart_scatter | ✅ pass | True |
| 07_survey_results.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 08_weather_data.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '7f5b76df'} |
| 08_weather_data.csv | filter | ✅ pass | {'status': 'ok', 'column': 'date', 'op': 'eq', 'value': ''} |
| 08_weather_data.csv | chart_bar | ✅ pass | True |
| 08_weather_data.csv | chart_line | ✅ pass | True |
| 08_weather_data.csv | chart_scatter | ✅ pass | True |
| 08_weather_data.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 09_ecommerce_orders.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': '73370e8d'} |
| 09_ecommerce_orders.csv | filter | ✅ pass | {'status': 'ok', 'column': 'order_id', 'op': 'eq', 'value': ''} |
| 09_ecommerce_orders.csv | chart_bar | ✅ pass | True |
| 09_ecommerce_orders.csv | chart_line | ✅ pass | True |
| 09_ecommerce_orders.csv | chart_scatter | ✅ pass | True |
| 09_ecommerce_orders.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| 10_bigdata_sample.csv | load | ✅ pass | {'status': 'ok', 'dataset_id': 'f5d214b9'} |
| 10_bigdata_sample.csv | filter | ✅ pass | {'status': 'ok', 'column': 'timestamp', 'op': 'eq', 'value': ''} |
| 10_bigdata_sample.csv | chart_bar | ✅ pass | True |
| 10_bigdata_sample.csv | chart_line | ✅ pass | True |
| 10_bigdata_sample.csv | chart_scatter | ✅ pass | True |
| 10_bigdata_sample.csv | clear_filters | ✅ pass | {'status': 'ok'} |
| test_comma.csv | load | ❌ fail | {'status': 'error', 'message': 'Engine failed to load dataset'} |
| test_comma.csv | filter | ✅ pass | {'status': 'ok', 'column': 'timestamp', 'op': 'eq', 'value': ''} |
| test_comma.csv | chart_bar | ✅ pass | True |
| test_comma.csv | chart_line | ✅ pass | True |
| test_comma.csv | chart_scatter | ✅ pass | True |
| test_comma.csv | clear_filters | ✅ pass | {'status': 'ok'} |

## Screenshots

### 01_sales_simple.csv / load
![load](docs/qa/01_sales_simple/graph_panel_20260223_093428.png)

### 01_sales_simple.csv / filter
![filter](docs/qa/01_sales_simple/graph_panel_20260223_093428.png)

### 01_sales_simple.csv / chart_bar
![chart_bar](docs/qa/01_sales_simple/graph_panel_20260223_093428.png)

### 01_sales_simple.csv / chart_line
![chart_line](docs/qa/01_sales_simple/graph_panel_20260223_093428.png)

### 01_sales_simple.csv / chart_scatter
![chart_scatter](docs/qa/01_sales_simple/graph_panel_20260223_093428.png)

### 01_sales_simple.csv / clear_filters
![clear_filters](/dev/null)

### 02_stock_ohlc.csv / load
![load](docs/qa/02_stock_ohlc/graph_panel_20260223_093428.png)

### 02_stock_ohlc.csv / filter
![filter](docs/qa/02_stock_ohlc/graph_panel_20260223_093429.png)

### 02_stock_ohlc.csv / chart_bar
![chart_bar](docs/qa/02_stock_ohlc/graph_panel_20260223_093429.png)

### 02_stock_ohlc.csv / chart_line
![chart_line](docs/qa/02_stock_ohlc/graph_panel_20260223_093429.png)

### 02_stock_ohlc.csv / chart_scatter
![chart_scatter](docs/qa/02_stock_ohlc/graph_panel_20260223_093429.png)

### 02_stock_ohlc.csv / clear_filters
![clear_filters](/dev/null)

### 03_sensors_timeseries.csv / load
![load](docs/qa/03_sensors_timeseries/graph_panel_20260223_093429.png)

### 03_sensors_timeseries.csv / filter
![filter](docs/qa/03_sensors_timeseries/graph_panel_20260223_093429.png)

### 03_sensors_timeseries.csv / chart_bar
![chart_bar](docs/qa/03_sensors_timeseries/graph_panel_20260223_093429.png)

### 03_sensors_timeseries.csv / chart_line
![chart_line](docs/qa/03_sensors_timeseries/graph_panel_20260223_093429.png)

### 03_sensors_timeseries.csv / chart_scatter
![chart_scatter](docs/qa/03_sensors_timeseries/graph_panel_20260223_093429.png)

### 03_sensors_timeseries.csv / clear_filters
![clear_filters](/dev/null)

### 04_employees.csv / load
![load](docs/qa/04_employees/graph_panel_20260223_093429.png)

### 04_employees.csv / filter
![filter](docs/qa/04_employees/graph_panel_20260223_093430.png)

### 04_employees.csv / chart_bar
![chart_bar](docs/qa/04_employees/graph_panel_20260223_093430.png)

### 04_employees.csv / chart_line
![chart_line](docs/qa/04_employees/graph_panel_20260223_093430.png)

### 04_employees.csv / chart_scatter
![chart_scatter](docs/qa/04_employees/graph_panel_20260223_093430.png)

### 04_employees.csv / clear_filters
![clear_filters](/dev/null)

### 05_products_inventory.csv / load
![load](docs/qa/05_products_inventory/graph_panel_20260223_093430.png)

### 05_products_inventory.csv / filter
![filter](docs/qa/05_products_inventory/graph_panel_20260223_093430.png)

### 05_products_inventory.csv / chart_bar
![chart_bar](docs/qa/05_products_inventory/graph_panel_20260223_093430.png)

### 05_products_inventory.csv / chart_line
![chart_line](docs/qa/05_products_inventory/graph_panel_20260223_093430.png)

### 05_products_inventory.csv / chart_scatter
![chart_scatter](docs/qa/05_products_inventory/graph_panel_20260223_093430.png)

### 05_products_inventory.csv / clear_filters
![clear_filters](/dev/null)

### 06_website_analytics.csv / load
![load](docs/qa/06_website_analytics/graph_panel_20260223_093431.png)

### 06_website_analytics.csv / filter
![filter](docs/qa/06_website_analytics/graph_panel_20260223_093431.png)

### 06_website_analytics.csv / chart_bar
![chart_bar](docs/qa/06_website_analytics/graph_panel_20260223_093431.png)

### 06_website_analytics.csv / chart_line
![chart_line](docs/qa/06_website_analytics/graph_panel_20260223_093431.png)

### 06_website_analytics.csv / chart_scatter
![chart_scatter](docs/qa/06_website_analytics/graph_panel_20260223_093431.png)

### 06_website_analytics.csv / clear_filters
![clear_filters](/dev/null)

### 07_survey_results.csv / load
![load](docs/qa/07_survey_results/graph_panel_20260223_093431.png)

### 07_survey_results.csv / filter
![filter](docs/qa/07_survey_results/graph_panel_20260223_093431.png)

### 07_survey_results.csv / chart_bar
![chart_bar](docs/qa/07_survey_results/graph_panel_20260223_093431.png)

### 07_survey_results.csv / chart_line
![chart_line](docs/qa/07_survey_results/graph_panel_20260223_093431.png)

### 07_survey_results.csv / chart_scatter
![chart_scatter](docs/qa/07_survey_results/graph_panel_20260223_093431.png)

### 07_survey_results.csv / clear_filters
![clear_filters](/dev/null)

### 08_weather_data.csv / load
![load](docs/qa/08_weather_data/graph_panel_20260223_093432.png)

### 08_weather_data.csv / filter
![filter](docs/qa/08_weather_data/graph_panel_20260223_093432.png)

### 08_weather_data.csv / chart_bar
![chart_bar](docs/qa/08_weather_data/graph_panel_20260223_093432.png)

### 08_weather_data.csv / chart_line
![chart_line](docs/qa/08_weather_data/graph_panel_20260223_093432.png)

### 08_weather_data.csv / chart_scatter
![chart_scatter](docs/qa/08_weather_data/graph_panel_20260223_093432.png)

### 08_weather_data.csv / clear_filters
![clear_filters](/dev/null)

### 09_ecommerce_orders.csv / load
![load](docs/qa/09_ecommerce_orders/graph_panel_20260223_093432.png)

### 09_ecommerce_orders.csv / filter
![filter](docs/qa/09_ecommerce_orders/graph_panel_20260223_093432.png)

### 09_ecommerce_orders.csv / chart_bar
![chart_bar](docs/qa/09_ecommerce_orders/graph_panel_20260223_093432.png)

### 09_ecommerce_orders.csv / chart_line
![chart_line](docs/qa/09_ecommerce_orders/graph_panel_20260223_093432.png)

### 09_ecommerce_orders.csv / chart_scatter
![chart_scatter](docs/qa/09_ecommerce_orders/graph_panel_20260223_093433.png)

### 09_ecommerce_orders.csv / clear_filters
![clear_filters](/dev/null)

### 10_bigdata_sample.csv / load
![load](docs/qa/10_bigdata_sample/graph_panel_20260223_093433.png)

### 10_bigdata_sample.csv / filter
![filter](docs/qa/10_bigdata_sample/graph_panel_20260223_093433.png)

### 10_bigdata_sample.csv / chart_bar
![chart_bar](docs/qa/10_bigdata_sample/graph_panel_20260223_093433.png)

### 10_bigdata_sample.csv / chart_line
![chart_line](docs/qa/10_bigdata_sample/graph_panel_20260223_093433.png)

### 10_bigdata_sample.csv / chart_scatter
![chart_scatter](docs/qa/10_bigdata_sample/graph_panel_20260223_093433.png)

### 10_bigdata_sample.csv / clear_filters
![clear_filters](/dev/null)

### test_comma.csv / load
![load](docs/qa/test_comma/graph_panel_20260223_093433.png)

### test_comma.csv / filter
![filter](docs/qa/test_comma/graph_panel_20260223_093433.png)

### test_comma.csv / chart_bar
![chart_bar](docs/qa/test_comma/graph_panel_20260223_093433.png)

### test_comma.csv / chart_line
![chart_line](docs/qa/test_comma/graph_panel_20260223_093433.png)

### test_comma.csv / chart_scatter
![chart_scatter](docs/qa/test_comma/graph_panel_20260223_093434.png)

### test_comma.csv / clear_filters
![clear_filters](/dev/null)
