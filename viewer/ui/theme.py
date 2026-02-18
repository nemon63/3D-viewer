def apply_ui_theme(widget, theme: str):
    if theme == "light":
        widget.setStyleSheet("")
        return

    if theme == "dark":
        widget.setStyleSheet(
            """
            QWidget { background: #1e1f22; color: #e4e7eb; }
            QLineEdit, QComboBox, QListWidget, QTreeWidget, QTabWidget::pane {
                background: #25272b; color: #e4e7eb; border: 1px solid #3a3d43;
            }
            QGroupBox {
                border: 1px solid #4a4f58; margin-top: 10px; padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #d7dbe1;
            }
            QTabBar::tab {
                background: #2b2f35; color: #d8dce3; padding: 5px 10px; border: 1px solid #3f444d;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background: #3a4049; color: #ffffff;
            }
            QPushButton { background: #2c2f35; border: 1px solid #454a52; padding: 5px 8px; }
            QPushButton:hover { background: #353941; }
            QSlider::groove:horizontal { background: #3a3d43; height: 6px; }
            QSlider::handle:horizontal { background: #7da3ff; width: 12px; margin: -4px 0; border-radius: 5px; }
            QToolBar { background: #1b1d20; border-bottom: 1px solid #3a3d43; spacing: 6px; }
            """
        )
        return

    # graphite
    widget.setStyleSheet(
        """
        QWidget { background: #2b2f36; color: #eceff4; }
        QLineEdit, QComboBox, QListWidget, QTreeWidget, QTabWidget::pane {
            background: #323741; color: #eceff4; border: 1px solid #4a5362;
        }
        QGroupBox {
            border: 1px solid #5c6678; margin-top: 10px; padding-top: 8px;
        }
        QGroupBox::title {
            subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #f0f3f8;
        }
        QTabBar::tab {
            background: #3a404c; color: #dce3ee; padding: 5px 10px; border: 1px solid #586273;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #566078; color: #ffffff;
        }
        QPushButton { background: #3a404c; border: 1px solid #586273; padding: 5px 8px; }
        QPushButton:hover { background: #444b58; }
        QSlider::groove:horizontal { background: #4a5362; height: 6px; }
        QSlider::handle:horizontal { background: #86b6ff; width: 12px; margin: -4px 0; border-radius: 5px; }
        QToolBar { background: #252a31; border-bottom: 1px solid #4a5362; spacing: 6px; }
        """
    )
