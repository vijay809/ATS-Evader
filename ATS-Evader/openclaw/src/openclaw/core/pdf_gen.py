import asyncio
import markdown
import os
from playwright.async_api import async_playwright

class PdfGenerator:
    """Utility class to convert Markdown strings to beautifully formatted PDFs using Headless Chromium."""
    
    @staticmethod
    async def markdown_to_pdf(md_text: str, output_path: str) -> str:
        """Converts Markdown text to a PDF file and returns the absolute path."""
        # Convert Markdown to HTML
        html_content = markdown.markdown(md_text, extensions=['tables', 'fenced_code'])
        
        # Wrap in a clean, ATS-friendly styling template
        full_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <style>
                @page {{
                    margin: 1in;
                    size: A4;
                }}
                body {{
                    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 800px;
                    margin: 0 auto;
                    font-size: 11pt;
                }}
                h1 {{
                    font-size: 24pt;
                    text-align: center;
                    border-bottom: 2px solid #333;
                    padding-bottom: 5px;
                    margin-bottom: 15px;
                }}
                h2 {{
                    font-size: 16pt;
                    border-bottom: 1px solid #ccc;
                    padding-bottom: 3px;
                    margin-top: 20px;
                    margin-bottom: 10px;
                }}
                h3 {{
                    font-size: 13pt;
                    margin-top: 15px;
                    margin-bottom: 5px;
                }}
                p {{
                    margin: 5px 0;
                }}
                ul, ol {{
                    margin-top: 5px;
                    margin-bottom: 10px;
                    padding-left: 20px;
                }}
                li {{
                    margin-bottom: 3px;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 15px;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }}
                strong {{
                    font-weight: 600;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Use headless Playwright to print to PDF
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Set the HTML content
            await page.set_content(full_html)
            
            # Wait a tiny bit for any font rendering (if we added web fonts)
            await page.wait_for_timeout(100)
            
            # Print to PDF
            await page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"} 
                # CSS handles margins
            )
            
            await browser.close()
            
        return os.path.abspath(output_path)
