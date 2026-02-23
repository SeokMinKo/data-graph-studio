"""App-specific panel stylesheet — part of the theme system.

Contains CSS for DGS application panels and custom widgets
(graph panels, legend, dataset manager, comparison panel, etc.).
Extracted from _theme_base_stylesheet.py.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .theme import Theme


def _hex_to_rgb(hex_color: str) -> str:
    """Convert hex color to RGB values for rgba()"""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f"{r}, {g}, {b}"
    return "0, 0, 0"


def panel_stylesheet(t: "Theme") -> str:
    """Return CSS for DGS application-specific panels.

    Args:
        t: Current Theme instance for color token access.

    Returns:
        QSS string for app-specific panel and custom widget styles.
    """
    return f"""/* ============ Panel Backgrounds ============ */
            #GraphOptionsPanel {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-right: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #LegendPanel {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-radius: 8px;
            }}
            
            #StatPanel {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-left: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            /* ============ Section Headers ============ */
            #sectionHeader {{
                font-weight: 600;
                font-size: 13px;
                color: {t.foreground};
                padding: 4px;
                background: transparent;
            }}
            
            /* ============ Hint & Stats Labels ============ */
            #hintLabel {{
                font-size: 10px;
                color: {t.text_muted};
                font-style: italic;
                background: transparent;
            }}
            
            #statsLabel {{
                font-size: 12px;
                color: {t.text_secondary};
                background: transparent;
            }}
            
            #seriesNameLabel {{
                font-size: 11px;
                color: {t.foreground};
                background: transparent;
            }}
            
            /* ============ Small Buttons ============ */
            #smallButton {{
                font-size: 10px;
                padding: 4px 8px;
            }}
            
            /* ============ Stat Cards ============ */
            #StatCard {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #StatCard:hover {{
                background-color: {t.surface_hover};
            }}
            
            #cardIcon {{
                font-size: 12px;
                background: transparent;
            }}
            
            #cardTitle {{
                color: {t.text_secondary};
                font-size: 10px;
                font-weight: 500;
                background: transparent;
                border: none;
            }}
            
            #cardValue {{
                color: {t.foreground};
                font-size: 18px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            
            #cardSubtitle {{
                color: {t.text_secondary};
                font-size: 9px;
                background: transparent;
                border: none;
            }}
            
            #cardSubtitle[trend="positive"] {{
                color: {t.success};
                font-weight: 500;
            }}
            
            #cardSubtitle[trend="negative"] {{
                color: {t.error};
                font-weight: 500;
            }}
            
            #cardSubtitle[trend="neutral"] {{
                color: {t.text_muted};
            }}
            
            /* ============ Context Label ============ */
            #contextLabel {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
                padding: 2px 8px;
                border-radius: 8px;
            }}
            
            #contextLabel[state="selection"] {{
                color: {t.success};
                background-color: {t.surface_hover};
                padding: 4px 12px;
                border-radius: 12px;
            }}
            
            #contextLabel[state="grouped"] {{
                color: {t.accent};
                background-color: {t.surface_hover};
                padding: 4px 12px;
                border-radius: 12px;
            }}
            
            /* ============ Drop Zones ============ */
            #XAxisZone {{
                background-color: {"#F0FDF4" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #GroupZone {{
                background-color: {"#F8FAFC" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #ValueZone {{
                background-color: {"#FAF5FF" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #HoverZone {{
                background-color: {"#FEFCE8" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #zoneIcon {{
                font-size: 16px;
                background: transparent;
            }}
            
            #zoneHeader {{
                font-weight: 600;
                font-size: 13px;
                background: transparent;
                color: {t.foreground};
            }}
            
            #zoneHeader[zone="x"] {{
                color: {"#047857" if t.is_light() else t.success};
            }}
            
            #zoneHeader[zone="group"] {{
                color: {t.foreground};
            }}
            
            #zoneHeader[zone="value"] {{
                color: {"#581C87" if t.is_light() else "#A78BFA"};
            }}
            
            #zoneHeader[zone="hover"] {{
                color: {"#854D0E" if t.is_light() else t.warning};
            }}
            
            #zoneHelp {{
                font-size: 10px;
                background: transparent;
                color: {t.text_secondary};
            }}
            
            #zoneHelp[zone="x"] {{
                color: {"#059669" if t.is_light() else t.success};
            }}
            
            #zoneHelp[zone="group"] {{
                color: {t.text_secondary};
            }}
            
            #zoneHelp[zone="value"] {{
                color: {"#9333EA" if t.is_light() else "#A78BFA"};
            }}
            
            #zoneHelp[zone="hover"] {{
                color: {"#A16207" if t.is_light() else t.warning};
            }}
            
            #dropZone {{
                background-color: {t.surface};
                border: 2px dashed {t.border};
                border-radius: 8px;
                min-height: 50px;
            }}
            
            #dropZone[state="filled"] {{
                background-color: {t.selected};
                border: 2px solid {t.success};
            }}
            
            #dropZone[state="dragover"] {{
                background-color: {t.surface_hover};
                border: 2px solid {t.success};
            }}
            
            #placeholder {{
                color: {t.text_muted};
                font-size: 12px;
                font-style: italic;
                background: transparent;
            }}
            
            #chipList {{
                background: transparent;
                border: none;
                outline: none;
            }}
            
            /* ============ Zone Buttons ============ */
            #zoneClearBtn {{
                background: transparent;
                color: {t.success};
                border: 1px solid {t.success};
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 500;
                font-size: 11px;
            }}
            
            #zoneClearBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.success};
            }}
            
            #dangerButton {{
                background: transparent;
                color: {t.error};
                border: 1px solid {t.error};
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 500;
                font-size: 10px;
            }}
            
            #dangerButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.error};
            }}
            
            #warningButton {{
                background: transparent;
                color: {t.warning};
                border: 1px solid {t.warning};
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 500;
                font-size: 10px;
            }}
            
            #warningButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.warning};
            }}
            
            /* ============ Data Table ============ */
            #dataTableView {{
                background-color: {t.surface};
                alternate-background-color: {t.surface_hover};
                selection-background-color: {t.selected};
                selection-color: {t.foreground};
                gridline-color: {t.border_light};
                border: none;
                border-radius: 8px;
                color: {t.foreground};
            }}
            
            #dataTableView::item {{
                padding: 4px 8px;
                color: {t.foreground};
            }}
            
            #dataTableView::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            #dataTableView::item:hover {{
                background-color: {t.hover};
            }}
            
            #dataTableView QHeaderView::section {{
                background-color: {t.surface};
                border: none;
                border-bottom: 1px solid {t.border};
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
                color: {t.foreground};
            }}
            
            #dataTableView QHeaderView::section:hover {{
                background-color: {t.surface_hover};
            }}
            
            /* ============ Sliding Window ============ */
            #slidingWindow {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 4px;
            }}
            
            /* ============ Side-by-Side Layout ============ */
            #statsFrame {{
                background-color: {t.surface};
                border-radius: 4px;
                padding: 4px;
            }}
            
            #syncOptionsFrame {{
                background-color: {t.surface};
                border-bottom: 1px solid {t.border};
            }}
            
            #graphPlaceholder {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                color: {t.foreground};
            }}
            
            /* ============ Floating Window ============ */
            #floatingHeader {{
                background-color: {t.surface};
                border-bottom: 1px solid {t.border};
            }}
            
            #floatingTitle {{
                font-size: 14px;
                font-weight: 600;
                color: {t.foreground};
                background: transparent;
            }}
            
            #floatingFooter {{
                background-color: {t.surface};
                border-top: 1px solid {t.border};
            }}
            
            #floatingStatus {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
            }}
            
            #floatingGraphContainer {{
                background-color: {t.background};
            }}
            
            #headerButton {{
                background: transparent;
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                color: {t.foreground};
            }}
            
            #headerButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.text_secondary};
            }}
            
            #headerButton:pressed {{
                background-color: {t.surface_active};
            }}
            
            #syncCheckbox {{
                color: {t.text_secondary};
                font-size: 12px;
                background: transparent;
            }}
            
            #headerSeparator {{
                background-color: {t.border};
            }}
            
            /* ============ Float Window ============ */
            #floatWindowHeader {{
                background-color: {t.surface};
                border-bottom: 1px solid {t.border};
            }}
            
            #dockButton {{
                background-color: {t.primary};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 500;
            }}
            
            #dockButton:hover {{
                background-color: {t.accent};
            }}
            
            #dockButton:pressed {{
                background-color: {t.primary};
            }}
            
            #sectionTitle {{
                font-weight: 600;
                font-size: 13px;
                color: {t.foreground};
                padding: 4px;
                background: transparent;
            }}
            
            #floatButton {{
                background-color: {t.surface_hover};
                border: 1px solid {t.border};
                border-radius: 4px;
                font-size: 12px;
                color: {t.text_secondary};
            }}
            
            #floatButton:hover {{
                background-color: {t.surface_active};
                border-color: {t.text_secondary};
                color: {t.foreground};
            }}
            
            #floatPlaceholder {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #floatPlaceholderLabel {{
                color: {t.text_muted};
                font-size: 12px;
                background: transparent;
            }}
            
            /* ============ Chip Widget ============ */
            #chipWidget {{
                background-color: {t.surface};
                border: 1px solid {t.text_secondary};
                border-radius: 10px;
            }}
            
            #chipWidget:hover {{
                background-color: {t.surface_active};
                border-color: {t.primary};
            }}
            
            #chipLabel {{
                font-size: 11px;
                font-weight: 600;
                color: {t.foreground};
                background: transparent;
            }}
            
            #chipRemoveBtn {{
                background: transparent;
                color: {t.text_muted};
                border: none;
                font-size: 12px;
                font-weight: bold;
            }}
            
            #chipRemoveBtn:hover {{
                background-color: {"#FEE2E2" if t.is_light() else t.surface_active};
                color: {t.error};
                border-radius: 8px;
            }}
            
            #dragHandle {{
                font-size: 10px;
                color: {t.text_muted};
                background: transparent;
            }}
            
            /* ============ Value Chip Widget ============ */
            #valueChipWidget {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 10px;
            }}
            
            #valueChipWidget:hover {{
                background-color: {t.surface_hover};
            }}
            
            #valueNameLabel {{
                font-weight: 600;
                font-size: 11px;
                color: {t.foreground};
                background: transparent;
            }}
            
            /* ============ Dialogs ============ */
            #dialogHeader {{
                font-size: 16px;
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #dialogPanel {{
                background-color: {t.surface};
                border: 1px solid {t.border};
            }}
            
            #dialogPanelLeft {{
                background-color: {t.surface_hover};
                border-right: 1px solid {t.border};
            }}
            
            #dialogFooter {{
                background-color: {t.surface};
                border-top: 1px solid {t.border};
            }}
            
            #settingItem {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px;
            }}
            
            #settingItem:hover {{
                background-color: {t.surface_hover};
            }}
            
            #settingIcon {{
                font-size: 24px;
                background: transparent;
            }}
            
            #settingName {{
                font-weight: 600;
                color: {t.foreground};
                font-size: 13px;
                background: transparent;
            }}
            
            #settingDetail {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
            }}
            
            #defaultBadge {{
                background-color: {"#FEF3C7" if t.is_light() else t.surface_active};
                color: {"#92400E" if t.is_light() else t.warning};
                font-size: 10px;
                padding: 2px 6px;
                border-radius: 4px;
            }}
            
            #actionButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
                font-size: 14px;
                color: {t.foreground};
            }}
            
            #actionButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.border};
            }}
            
            #primaryButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            
            #primaryButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.accent}, stop:1 {t.primary});
            }}
            
            #secondaryButton {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 8px 16px;
            }}
            
            #secondaryButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            #deleteButton {{
                background-color: {"#FEE2E2" if t.is_light() else t.surface};
                color: {t.error};
                border: 1px solid {t.error};
                border-radius: 6px;
                padding: 8px 16px;
            }}
            
            #deleteButton:hover {{
                background-color: {t.error};
                color: white;
            }}
            
            /* ============ Profile Bar ============ */
            #profileBar {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #profileIcon {{
                font-size: 18px;
                background: transparent;
            }}
            
            #profileName {{
                font-weight: 600;
                font-size: 13px;
                color: {t.foreground};
                background: transparent;
            }}
            
            #profileActiveLabel {{
                color: {t.success};
                font-size: 12px;
            }}
            
            #profileActionBtn {{
                background: transparent;
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {t.text_secondary};
            }}
            
            #profileActionBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
                color: {t.primary};
            }}
            
            #profileLabel {{
                color: {t.text_secondary};
                font-size: 12px;
                background: transparent;
            }}
            
            /* ============ Dataset Manager ============ */
            #datasetItem {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #datasetItem:hover {{
                background-color: {t.surface_hover};
            }}
            
            #datasetItem[active="true"] {{
                border: 2px solid {t.success};
            }}
            
            #datasetName {{
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #datasetActiveLabel {{
                color: {t.success};
                font-size: 12px;
            }}
            
            #datasetStat {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #datasetRemoveBtn {{
                color: {t.error};
            }}
            
            #datasetTitle {{
                font-size: 14px;
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #datasetTree {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #datasetAddBtn {{
                background-color: {t.primary};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }}
            
            #datasetAddBtn:hover {{
                background-color: {t.accent};
            }}
            
            /* ============ Overlay Stats ============ */
            #overlayStatsWidget {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #overlayTitle {{
                font-weight: bold;
                font-size: 12px;
                color: {t.foreground};
            }}
            
            #overlayStatLabel {{
                font-size: 9px;
                color: {t.text_muted};
            }}
            
            #overlayStatValue {{
                font-size: 10px;
                color: {t.foreground};
            }}
            
            #overlayStatPositive {{
                font-size: 10px;
                font-weight: bold;
                color: {t.success};
            }}
            
            /* ============ Comparison Panel ============ */
            #guideText {{
                padding: 4px;
                background-color: {t.surface_hover};
                border-radius: 4px;
                color: {t.foreground};
            }}
            
            #diffSummary {{
                padding: 8px;
                background-color: {t.surface_hover};
                border-radius: 4px;
                color: {t.foreground};
            }}
            
            /* ============ Search Input ============ */
            #searchInput {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                padding-right: 32px;
                placeholder-text-color: {t.text_secondary};
            }}
            
            #searchInput:focus {{
                border: 2px solid {t.primary};
            }}
            
            #searchClearBtn {{
                background: transparent;
                border: none;
                color: {t.text_muted};
                font-size: 14px;
            }}
            
            #searchClearBtn:hover {{
                color: {t.foreground};
            }}
            
            #searchResultLabel {{
                font-size: 10px;
                color: {t.text_muted};
                background: transparent;
            }}
            
            #searchResultLabel[state="found"] {{
                color: {t.success};
            }}
            
            #searchResultLabel[state="notfound"] {{
                color: {t.error};
            }}
            
            /* ============ Limit Marking Button ============ */
            #limitMarkingBtn {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
                color: {t.text_secondary};
            }}
            
            #limitMarkingBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            #limitMarkingBtn:checked {{
                background-color: {t.selected};
                border-color: {t.primary};
                color: {t.primary};
            }}
            
            /* ============ Window/Group Info Labels ============ */
            #windowLabel {{
                color: {t.text_secondary};
                font-size: 10px;
            }}
            
            #groupInfoLabel {{
                color: {t.text_secondary};
                font-size: 10px;
            }}
            
            #groupInfoLabel[state="grouped"] {{
                color: {t.primary};
                font-weight: 500;
            }}
            
            /* ============ Splitter ============ */
            #themeSplitter::handle {{
                background-color: {t.text_muted if not t.is_light() else t.border};
            }}
            
            /* ============ Toolbar Labels ============ */
            #toolbarLabel {{
                color: {t.text_secondary};
                font-size: 12px;
            }}
            
            /* ============ Max Points Label ============ */
            #maxPointsLabel {{
                font-weight: 600;
                color: {t.accent};
            }}
            
            /* ============ Error/Warning Labels ============ */
            #errorLabel {{
                color: {t.error};
            }}
            
            #warningLabel {{
                color: {t.warning};
            }}
            
            #successLabel {{
                color: {t.success};
            }}
            
            /* ============ Parsing Preview ============ */
            #previewHeader {{
                font-size: 16px;
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #etlStatusLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #etlStatusLabel[state="success"] {{
                color: {t.success};
            }}
            
            #etlStatusLabel[state="error"] {{
                color: {t.error};
            }}
            
            #statsCountLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #columnCountLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            /* ============ Save Setting Dialog ============ */
            #dialogLine {{
                background-color: {t.border};
            }}
            
            #inputLabel {{
                font-weight: 500;
                color: {t.foreground};
            }}
            
            #optionsFrame {{
                background-color: {t.surface_hover};
                border-radius: 8px;
            }}
            
            #optionCheckbox {{
                color: {t.text_secondary};
            }}
            
            /* ============ Multi File Dialog ============ */
            #fileHeader {{
                color: {t.text_muted};
            }}
            
            #summaryLabel {{
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #warningBox {{
                color: {"#f57c00" if t.is_light() else t.warning};
                padding: 8px;
                background-color: {"#fff3e0" if t.is_light() else t.surface_hover};
                border-radius: 4px;
            }}
            
            /* ============ Report Dialog ============ */
            #generateBtn {{
                background-color: {t.success};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            
            #generateBtn:hover {{
                background-color: {"#059669" if t.is_light() else "#34D399"};
            }}
            
            /* ============ Drawing ============ */
            #drawingStyleFrame {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            /* ============ Dashboard ============ */
            #dashboardTitle {{
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #chartArea {{
                background-color: {t.surface_hover};
            }}
            
            /* ============ Side by Side Header ============ */
            #datasetHeaderFrame {{
                border-radius: 4px;
            }}
            
            #datasetHeaderName {{
                color: white;
                font-weight: bold;
            }}
            
            #datasetHeaderRows {{
                color: rgba(255,255,255,0.8);
            }}
            
            /* ============ Empty State (New) ============ */
            #emptyStateWidget {{
                background-color: {t.background};
            }}
            
            #emptyStateCard {{
                background-color: {t.surface};
                border: {"1px solid " + t.border if t.is_light() else "none"};
                border-radius: 16px;
            }}
            
            #emptyStateIcon {{
                background: transparent;
                border: none;
            }}
            
            #emptyStateTitle {{
                font-size: 24px;
                font-weight: 700;
                color: {t.foreground};
                background: transparent;
                border: none;
                margin-top: 8px;
            }}
            
            #emptyStateSubtitle {{
                font-size: 15px;
                color: {t.text_secondary};
                background: transparent;
                border: none;
                line-height: 1.5;
            }}
            
            #emptyStateFormats {{
                font-size: 12px;
                color: {t.text_muted};
                background: transparent;
                border: none;
                margin-top: 4px;
            }}
            
            #emptyStatePrimaryBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
                min-width: 120px;
            }}
            
            #emptyStatePrimaryBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.accent}, stop:1 {t.primary});
            }}
            
            #emptyStateSecondaryBtn {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 500;
                min-width: 120px;
            }}
            
            #emptyStateSecondaryBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            #emptyStateDropHint {{
                background-color: {"#F0FDF4" if t.is_light() else "rgba(16, 185, 129, 0.1)"};
                border: 2px dashed {"#86EFAC" if t.is_light() else t.success};
                border-radius: 12px;
            }}
            
            #dropHintIcon {{
                font-size: 24px;
                background: transparent;
                border: none;
            }}
            
            #dropHintText {{
                font-size: 13px;
                color: {t.success};
                background: transparent;
                border: none;
            }}
            
            #emptyStateStepsTitle {{
                font-size: 13px;
                font-weight: 600;
                color: {t.text_secondary};
                background: transparent;
                border: none;
                margin-bottom: 8px;
            }}
            
            #stepNumber {{
                font-size: 16px;
                background: transparent;
                border: none;
            }}
            
            #stepText {{
                font-size: 13px;
                color: {t.text_secondary};
                background: transparent;
                border: none;
            }}
            
            /* ============ Drop Overlay ============ */
            #dropZoneOverlay {{
                background-color: rgba({_hex_to_rgb(t.primary)}, 0.15);
                border: 3px dashed {t.primary};
            }}
            
            #dropOverlayIcon {{
                background: transparent;
                border: none;
            }}
            
            #dropOverlayText {{
                font-size: 18px;
                font-weight: 600;
                color: {t.primary};
                background: transparent;
                border: none;
            }}
            
            /* ============ Improved Drop Zones ============ */
            #XAxisZone {{
                background-color: {"#ECFDF5" if t.is_light() else "rgba(16, 185, 129, 0.08)"};
                border: 2px dashed {"#A7F3D0" if t.is_light() else "rgba(16, 185, 129, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #XAxisZone[state="filled"] {{
                background-color: {"#D1FAE5" if t.is_light() else "rgba(16, 185, 129, 0.15)"};
                border: 2px solid {t.success};
            }}
            
            #XAxisZone[state="dragover"] {{
                background-color: {"#A7F3D0" if t.is_light() else "rgba(16, 185, 129, 0.25)"};
                border: 2px solid {t.success};
            }}
            
            #GroupZone {{
                background-color: {"#F8FAFC" if t.is_light() else "rgba(148, 163, 184, 0.08)"};
                border: 2px dashed {"#CBD5E1" if t.is_light() else "rgba(148, 163, 184, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #GroupZone[state="filled"] {{
                background-color: {"#E2E8F0" if t.is_light() else "rgba(148, 163, 184, 0.15)"};
                border: 2px solid {t.text_secondary};
            }}
            
            #ValueZone {{
                background-color: {"#EEF2FF" if t.is_light() else "rgba(99, 102, 241, 0.08)"};
                border: 2px dashed {"#C7D2FE" if t.is_light() else "rgba(99, 102, 241, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #ValueZone[state="filled"] {{
                background-color: {"#E0E7FF" if t.is_light() else "rgba(99, 102, 241, 0.15)"};
                border: 2px solid {t.primary};
            }}
            
            #HoverZone {{
                background-color: {"#FFFBEB" if t.is_light() else "rgba(245, 158, 11, 0.08)"};
                border: 2px dashed {"#FDE68A" if t.is_light() else "rgba(245, 158, 11, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #HoverZone[state="filled"] {{
                background-color: {"#FEF3C7" if t.is_light() else "rgba(245, 158, 11, 0.15)"};
                border: 2px solid {t.warning};
            }}
            
            /* ============ Enhanced Placeholder Text ============ */
            #placeholder {{
                color: {t.text_muted};
                font-size: 13px;
                font-weight: 500;
                background: transparent;
            }}
            
            /* ============ Graph Area Enhancement ============ */
            #graphAreaFrame {{
                background-color: {t.background};
                border-radius: 8px;
            }}
"""
