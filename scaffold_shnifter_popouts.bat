@echo off
REM Batch script to scaffold multiple new PySide6 popouts for Shnifter
cd /d %~dp0

REM 1. 3D Data Visualization Popout
copy nul shnifter_frontend\shnifter_3d_visualization_popout.py >nul

REM 2. Advanced Chart Dashboard Popout
copy nul shnifter_frontend\advanced_chart_dashboard_popout.py >nul

REM 3. Data Table Explorer Popout
copy nul shnifter_frontend\data_table_explorer_popout.py >nul

REM 4. PDF Export Popout
copy nul shnifter_frontend\pdf_export_popout.py >nul

REM 5. Web News/Content Popout
copy nul shnifter_frontend\web_content_popout.py >nul

REM 6. Bluetooth Device Popout
copy nul shnifter_frontend\bluetooth_device_popout.py >nul

REM 7. Alerts/Annotation Popout
copy nul shnifter_frontend\alerts_annotation_popout.py >nul

echo Popout scaffolding complete. Edit each .py file to implement features.
pause
