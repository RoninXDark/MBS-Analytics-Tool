MBS ANALYTICS TOOL - CLIENT EDITION
==================================================

QUICK START
--------------------------------------------------
1. No installation required.
2. Simply double-click "MBS_Analytics_Tool.exe" to launch.

IMPORTANT: WHERE ARE MY CHARTS?
--------------------------------------------------
The tool automatically saves all charts and reports IN THE SAME FOLDER 
as your input Excel/CSV data file.

> Example: If you load data from your "Downloads" folder, 
> the output folders will appear in "Downloads" next to your file.

--------------------------------------------------
USER GUIDE
--------------------------------------------------

TAB 1: PRICE HISTORY & BATCH PROCESSING
1. Click "Browse" and select your Bloomberg Data file.
2. Click "LOAD DATA" (Required step to index the file).
3. Choose your workflow:
   - OPTION A (Single Bond): Type a name in the Filter box (e.g., "FNCL 4") 
     and click "GENERATE CHARTS". The chart will open instantly.
   - OPTION B (Batch): Leave the Filter box BLANK and click "GENERATE CHARTS".
     This will generate individual charts for ALL bonds (~800+) and save them 
     to the "MBS_PRICES_OUTPUT" folder.

TAB 2: SPREAD CALCULATOR (Interactive)
1. Ensure Price Data is loaded in Tab 1.
2. Select "Bond A" (Long) and "Bond B" (Short) from the lists.
3. Select Timeline (e.g., "3 Months", "YTD").
4. Click "PLOT SPREAD".
   > This generates a differential chart (Bond A minus Bond B) with a zero-axis.
   > Saved in: "MBS_SPREADS" folder.

TAB 3: RESIDUALS ANALYSIS (Rich/Cheap)
1. Click "LOAD RESIDUALS FILE" (e.g., your R-Studio output).
   *Note: Ensure the file contains historical data for line charting.*
2. Two Analysis Modes:
   - HISTORICAL LINE (Specific Bond): Select a bond from the dropdown and 
     click "CHART RESIDUAL (LINE)". Shows the trend vs Zero line.
   - MARKET OVERVIEW (All Bonds): Click "GENERATE MARKET OVERVIEW". 
     Creates a Scatter Plot and the "REPORT_RICH_CHEAP.xlsx" (Top 10 Rich/Cheap).
   > Saved in: "MBS_RESIDUALS_OUTPUT" folder.

--------------------------------------------------
NOTES
--------------------------------------------------
* All prices and residuals are converted to 32nds notation (e.g., 0-12+).
* Date axes are formatted as MM/DD/YY.
* Charts include a fixed zero-line for easy Rich/Cheap identification.

Support: Stanislav Mykhailytskyi