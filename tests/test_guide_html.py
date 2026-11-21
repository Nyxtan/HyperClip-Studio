#!/usr/bin/env python3
"""
Test Suite: HTML Interactive Guide Verification
------------------------------------------------
Validates that ai_clipper_guide.html and ai_clipper_guide.html conform to production standards,
contain all required interactive widgets, agent selectors, clipboard functions,
comparison matrices, and print stylesheets.
"""

import os
import re
import pytest

GUIDE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(GUIDE_DIR, "ai_clipper_guide.html")
DUPLICATE_PATH = os.path.join(GUIDE_DIR, "ai_clipper_guide.html")

@pytest.fixture(scope="module")
def html_content():
    assert os.path.exists(INDEX_PATH), f"Missing ai_clipper_guide.html at {INDEX_PATH}"
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return f.read()

def test_html_files_exist():
    """Verify both ai_clipper_guide.html and ai_clipper_guide.html exist and match."""
    assert os.path.isfile(INDEX_PATH)
    assert os.path.isfile(DUPLICATE_PATH)
    with open(INDEX_PATH, "r", encoding="utf-8") as f1, open(DUPLICATE_PATH, "r", encoding="utf-8") as f2:
        c1 = f1.read()
        c2 = f2.read()
        assert len(c1) == len(c2), "ai_clipper_guide.html and ai_clipper_guide.html lengths do not match"
        assert c1 == c2, "ai_clipper_guide.html and ai_clipper_guide.html content is not identical"

def test_html5_doctype_and_metadata(html_content):
    """Verify HTML5 DOCTYPE, viewport, and title."""
    assert "<!DOCTYPE html>" in html_content
    assert '<meta name="viewport"' in html_content
    assert "<title>" in html_content
    assert "AI Clipper" in html_content

def test_cyberpunk_color_palette(html_content):
    """Verify cyberpunk glassmorphism CSS custom properties exist."""
    assert "--bg-base: #0B0F19" in html_content
    assert "--neon-violet: #8B5CF6" in html_content
    assert "--neon-cyan: #06B6D4" in html_content
    assert "--neon-emerald: #10B981" in html_content
    assert "--neon-amber: #F59E0B" in html_content

def test_dual_camera_section(html_content):
    """Verify dual-camera iPad guide, 3-clap sync protocol, and calculator."""
    assert 'id="dual-camera-workflow"' in html_content
    assert "Dual-Camera iPad" in html_content
    assert "3-Clap Slate Protocol" in html_content
    assert "Blackmagic Camera" in html_content
    assert "cross-correlation" in html_content.lower()

def test_interactive_calculator_elements(html_content):
    """Verify the interactive calculator inputs and live preview elements."""
    assert 'id="input-pip-size"' in html_content
    assert 'id="input-margin"' in html_content
    assert 'id="select-pos"' in html_content
    assert 'id="select-shape"' in html_content
    assert 'id="mockup-screen"' in html_content
    assert 'id="mockup-pip"' in html_content
    assert "updatePipPreview" in html_content

def test_repo_comparison_matrix(html_content):
    """Verify GitHub repositories comparison matrix and interactive filters."""
    assert 'id="repo-comparison"' in html_content
    assert 'id="matrix-table"' in html_content
    assert "OpenSource-Clipping" in html_content
    assert "OpenShorts" in html_content
    assert "GTA-Auto-Clipper" in html_content
    assert "filterTable" in html_content
    assert "Google Colab" in html_content

def test_g6_live_chat_velocity_section(html_content):
    """Verify G6 live chat burst and comment trigger section."""
    assert 'id="g6-comment-clipping"' in html_content
    assert "G6 Live Stream" in html_content
    assert "!clip" in html_content
    assert "Chat Velocity" in html_content

def test_social_auto_posting_blotato_section(html_content):
    """Verify Blotato ('Bloro') and social auto-posting section."""
    assert 'id="social-auto-posting"' in html_content
    assert "Blotato" in html_content
    assert "Bloro" in html_content
    assert "Instagram Reels" in html_content
    assert "TikTok" in html_content
    assert "YouTube Shorts" in html_content

def test_agent_tabs_and_selector(html_content):
    """Verify interactive coding agent switcher and panel content."""
    assert 'id="coding-agent-prompts"' in html_content
    assert "Universal Prompt" in html_content
    assert "Cursor Composer" in html_content
    assert "Claude Code" in html_content
    assert "switchAgentTab" in html_content
    assert 'id="panel-universal"' in html_content
    assert 'id="panel-cursor"' in html_content
    assert 'id="panel-claude"' in html_content
    assert 'id="panel-terminal"' in html_content

def test_clipboard_copy_buttons(html_content):
    """Verify functional 1-click copy buttons and JS handler."""
    assert "copyCode" in html_content
    assert "navigator.clipboard.writeText" in html_content
    assert "copy-btn" in html_content
    assert "Copied! ✓" in html_content

def test_free_api_keys_guide(html_content):
    """Verify free API keys section and resource links."""
    assert 'id="free-api-keys"' in html_content
    assert "Google Gemini 2.0 Flash" in html_content
    assert "Pexels API" in html_content
    assert "aistudio.google.com" in html_content

def test_print_stylesheet_support(html_content):
    """Verify clean print styles for PDF export via browser."""
    assert "@media print" in html_content
    assert "window.print()" in html_content
