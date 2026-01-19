from PySide6.QtWidgets import QApplication

def get_font_size_pt(base_size_pt=10.0):
    """
    Calculates a DPI-scaled font size in points.
    
    Args:
        base_size_pt (float): The base font size in points at 96 DPI.
        
    Returns:
        float: The adjusted font size for the current screen DPI.
    """
    screen = QApplication.primaryScreen()
    if not screen:
        # Fallback for environments without a primary screen
        return base_size_pt
        
    dpi = screen.logicalDotsPerInch()
    
    # 96 DPI is the standard for 100% scaling in Windows.
    # We calculate a scaling factor and apply it to the base size.
    scale_factor = dpi / 96.0
    
    return base_size_pt * scale_factor

def get_summary_font_size_pt():
    """Returns a slightly larger font size for the summary label."""
    return get_font_size_pt(base_size_pt=11.0)

def get_list_item_font_size_pt():
    """Returns the standard font size for list items."""
    return get_font_size_pt(base_size_pt=10.0)
