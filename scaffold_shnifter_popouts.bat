@echo off
setlocal
cd /d "%~dp0" || exit /b 1
REM Never overwrite existing prototype work.
for %%F in (shnifter_3d_visualization_popout advanced_chart_dashboard_popout data_table_explorer_popout pdf_export_popout web_content_popout bluetooth_device_popout alerts_annotation_popout) do (
    if not exist "shnifter_frontend\%%F.py" (
        type nul > "shnifter_frontend\%%F.py"
        if errorlevel 1 exit /b 1
    )
)
echo Missing popout files created; existing files preserved.
exit /b 0
