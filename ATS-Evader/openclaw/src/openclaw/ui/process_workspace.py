"""Process Workspace for the Job Pipeline Loop."""
from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QSplitter, QScrollArea, QFrame,
    QTextEdit
)

if TYPE_CHECKING:
    from openclaw.core.runtime import Runtime


class ProcessWorkspace(QWidget):
    """The central dashboard for agent interaction and job approvals."""

    def __init__(self, runtime: 'Runtime') -> None:
        super().__init__()
        self._runtime = runtime

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- LEFT SIDEBAR (Preferences) --
        sidebar = QWidget()
        sidebar.setStyleSheet("background-color: #1a1a1a; border-right: 1px solid #333;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(24, 24, 24, 24)
        sidebar_layout.setSpacing(16)

        header = QLabel("Target Profile")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #e5e2e1; border: none;")
        sidebar_layout.addWidget(header)

        # Dynamic Preferences area (we will populate this from DB)
        self._pref_layout = QVBoxLayout()
        sidebar_layout.addLayout(self._pref_layout)

        sidebar_layout.addStretch()

        self._start_btn = QPushButton("Start Job Hunt")
        self._start_btn.setMinimumHeight(48)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background-color: #adc6ff; color: #002e69; 
                border-radius: 8px; font-size: 16px; font-weight: bold;
            }
        """)
        sidebar_layout.addWidget(self._start_btn)

        # -- RIGHT MAIN AREA (Chat/Feed) --
        main_area = QWidget()
        main_area.setStyleSheet("background-color: #131313;")
        main_area_layout = QVBoxLayout(main_area)
        main_area_layout.setContentsMargins(24, 24, 24, 24)
        
        # Scrollable feed
        feed_scroll = QScrollArea()
        feed_scroll.setWidgetResizable(True)
        feed_scroll.setStyleSheet("border: none; background: transparent;")
        
        self._feed_widget = QWidget()
        self._feed_widget.setStyleSheet("background: transparent;")
        self._feed_layout = QVBoxLayout(self._feed_widget)
        self._feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        feed_scroll.setWidget(self._feed_widget)
        
        main_area_layout.addWidget(feed_scroll, stretch=1)

        # Chat Input
        chat_layout = QHBoxLayout()
        self._chat_input = QLineEdit()
        self._chat_input.setPlaceholderText("Refine search parameters or ask a question...")
        self._chat_input.setMinimumHeight(48)
        self._chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #1c1b1b; color: white; border: 1px solid #333; 
                border-radius: 24px; padding: 0 16px; font-size: 14px;
            }
        """)
        
        send_btn = QPushButton("Send")
        send_btn.setMinimumHeight(48)
        send_btn.setStyleSheet("background-color: transparent; color: #adc6ff; font-weight: bold; border: none;")
        
        chat_layout.addWidget(self._chat_input)
        chat_layout.addWidget(send_btn)
        main_area_layout.addLayout(chat_layout)

        # Add to splitter
        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        main_layout.addWidget(splitter)
        self.refresh_preferences()

    def refresh_preferences(self) -> None:
        """Load preferences from SQLite and display them in the sidebar."""
        # Clear existing
        while self._pref_layout.count():
            child = self._pref_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        try:
            prefs = self._runtime.plugins._context.documents.get_preferences()
            for pref in prefs:
                card = QFrame()
                card.setStyleSheet("background-color: #2a2a2a; border-radius: 8px; padding: 12px; border: none;")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(0,0,0,0)
                
                k_lbl = QLabel(pref.key.upper())
                k_lbl.setStyleSheet("color: #8b90a0; font-size: 10px; font-weight: bold; font-family: monospace; border: none;")
                v_lbl = QLabel(pref.value)
                v_lbl.setStyleSheet("color: white; font-size: 14px; border: none;")
                
                card_layout.addWidget(k_lbl)
                card_layout.addWidget(v_lbl)
                self._pref_layout.addWidget(card)
        except Exception:
            pass

    def add_job_card(self, title: str, company: str, match_score: int, analysis: list[str]) -> None:
        """Adds a job match card to the feed."""
        card = QFrame()
        card.setStyleSheet("background-color: #1c1b1b; border: 1px solid #adc6ff; border-radius: 12px; padding: 16px;")
        layout = QVBoxLayout(card)
        
        # Header
        header_layout = QHBoxLayout()
        title_lbl = QLabel(f"{title} @ {company}")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white; border: none;")
        score_lbl = QLabel(f"{match_score}% Match")
        score_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ecb2ff; border: none;")
        
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        header_layout.addWidget(score_lbl)
        layout.addLayout(header_layout)

        # Analysis
        for point in analysis:
            p_lbl = QLabel(f"• {point}")
            p_lbl.setStyleSheet("color: #c1c6d7; font-size: 14px; border: none;")
            layout.addWidget(p_lbl)

        # Actions
        actions_layout = QHBoxLayout()
        approve_btn = QPushButton("Approve & Apply")
        approve_btn.setMinimumHeight(40)
        approve_btn.setStyleSheet("background-color: #4b8eff; color: white; border-radius: 6px; font-weight: bold;")
        
        skip_btn = QPushButton("Skip")
        skip_btn.setMinimumHeight(40)
        skip_btn.setStyleSheet("background-color: transparent; border: 1px solid #555; color: white; border-radius: 6px;")
        
        actions_layout.addWidget(approve_btn)
        actions_layout.addWidget(skip_btn)
        layout.addLayout(actions_layout)

        self._feed_layout.addWidget(card)
