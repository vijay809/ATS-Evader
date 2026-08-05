"""Extracts and annotates interactive DOM elements for LLM consumption."""

from __future__ import annotations

import json
from dataclasses import dataclass

from playwright.async_api import Page


@dataclass
class DOMElement:
    agent_id: int
    tag: str
    role: str
    text: str
    placeholder: str
    
    def to_markdown(self) -> str:
        parts = [f"[{self.agent_id}] {self.tag}"]
        if self.role:
            parts.append(f"role={self.role}")
        if self.text:
            parts.append(f"text='{self.text}'")
        if self.placeholder:
            parts.append(f"placeholder='{self.placeholder}'")
        return " ".join(parts)


EXTRACT_JS = """
() => {
    let idCounter = 1;
    const elements = [];
    
    // Select interactive elements
    const nodes = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"], [role="menuitem"]');
    
    for (const node of nodes) {
        // Skip hidden elements
        const style = window.getComputedStyle(node);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
        const rect = node.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        
        // Annotate
        const id = idCounter++;
        node.setAttribute('data-agent-id', id.toString());
        
        // Extract features
        let text = node.innerText || node.textContent || node.value || '';
        text = text.trim().substring(0, 50);
        
        elements.push({
            agent_id: id,
            tag: node.tagName.toLowerCase(),
            role: node.getAttribute('role') || '',
            text: text,
            placeholder: node.getAttribute('placeholder') || ''
        });
    }
    return JSON.stringify(elements);
}
"""


class DOMExtractor:
    """Provides methods to parse page state into a clean format."""
    
    @staticmethod
    async def get_interactive_state(page: Page) -> str:
        """Injects IDs and returns a markdown representation of the page."""
        raw_json = await page.evaluate(EXTRACT_JS)
        data = json.loads(raw_json)
        
        lines = ["# Current Page State", "Interactive Elements:"]
        for item in data:
            el = DOMElement(**item)
            lines.append("- " + el.to_markdown())
            
        if len(lines) == 2:
            lines.append("- (No interactive elements found)")
            
        return "\\n".join(lines)
