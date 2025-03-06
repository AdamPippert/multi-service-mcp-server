# tools/puppeteer_tool.py
from flask import Blueprint, request, jsonify, current_app
import os
import json
import base64
import tempfile
import subprocess
from pathlib import Path
import asyncio
import threading

puppeteer_routes = Blueprint('puppeteer', __name__)

# Path to the Node.js scripts
SCRIPT_DIR = Path(__file__).parent.parent / 'node_scripts'

def ensure_script_dir():
    """Ensure the puppeteer scripts directory exists and create necessary scripts"""
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    
    # Create the screenshot script if it doesn't exist
    screenshot_script = SCRIPT_DIR / 'screenshot.js'
    if not screenshot_script.exists():
        with open(screenshot_script, 'w') as f:
            f.write("""
const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
  const args = JSON.parse(process.argv[2]);
  const browser = await puppeteer.launch({
    headless: args.headless !== false,
    executablePath: args.executablePath || null,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const page = await browser.newPage();
  
  if (args.viewport) {
    await page.setViewport(args.viewport);
  }
  
  if (args.userAgent) {
    await page.setUserAgent(args.userAgent);
  }
  
  await page.goto(args.url, { 
    waitUntil: args.waitUntil || 'networkidle2',
    timeout: args.timeout || 30000
  });
  
  if (args.waitForSelector) {
    await page.waitForSelector(args.waitForSelector, { timeout: args.selectorTimeout || 30000 });
  }
  
  if (args.waitTime) {
    await new Promise(resolve => setTimeout(resolve, args.waitTime));
  }
  
  const screenshotOptions = {
    path: args.outputPath,
    fullPage: args.fullPage === true,
    type: args.type || 'png',
    quality: args.type === 'jpeg' ? (args.quality || 80) : undefined
  };
  
  await page.screenshot(screenshotOptions);
  await browser.close();
  
  console.log(JSON.stringify({ success: true, outputPath: args.outputPath }));
})().catch(err => {
  console.error(JSON.stringify({ success: false, error: err.message }));
  process.exit(1);
});
            """)
    
    # Create the PDF script if it doesn't exist
    pdf_script = SCRIPT_DIR / 'pdf.js'
    if not pdf_script.exists():
        with open(pdf_script, 'w') as f:
            f.write("""
const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
  const args = JSON.parse(process.argv[2]);
  const browser = await puppeteer.launch({
    headless: args.headless !== false,
    executablePath: args.executablePath || null,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const page = await browser.newPage();
  
  if (args.viewport) {
    await page.setViewport(args.viewport);
  }
  
  if (args.userAgent) {
    await page.setUserAgent(args.userAgent);
  }
  
  await page.goto(args.url, { 
    waitUntil: args.waitUntil || 'networkidle2',
    timeout: args.timeout || 30000
  });
  
  if (args.waitForSelector) {
    await page.waitForSelector(args.waitForSelector, { timeout: args.selectorTimeout || 30000 });
  }
  
  if (args.waitTime) {
    await new Promise(resolve => setTimeout(resolve, args.waitTime));
  }
  
  const pdfOptions = {
    path: args.outputPath,
    format: args.format || 'A4',
    printBackground: args.printBackground !== false,
    margin: args.margin || { top: '1cm', right: '1cm', bottom: '1cm', left: '1cm' }
  };
  
  await page.pdf(pdfOptions);
  await browser.close();
  
  console.log(JSON.stringify({ success: true, outputPath: args.outputPath }));
})().catch(err => {
  console.error(JSON.stringify({ success: false, error: err.message }));
  process.exit(1);
});
            """)
    
    # Create the content extraction script if it doesn't exist
    extract_script = SCRIPT_DIR / 'extract.js'
    if not extract_script.exists():
        with open(extract_script, 'w') as f:
            f.write("""
const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
  const args = JSON.parse(process.argv[2]);
  const browser = await puppeteer.launch({
    headless: args.headless !== false,
    executablePath: args.executablePath || null,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  
  const page = await browser.newPage();
  
  if (args.userAgent) {
    await page.setUserAgent(args.userAgent);
  }
  
  await page.goto(args.url, { 
    waitUntil: args.waitUntil || 'networkidle2',
    timeout: args.timeout || 30000
  });
  
  if (args.waitForSelector) {
    await page.waitForSelector(args.waitForSelector, { timeout: args.selectorTimeout || 30000 });
  }
  
  if (args.waitTime) {
    await new Promise(resolve => setTimeout(resolve, args.waitTime));
  }
  
  let result;
  
  if (args.selector) {
    if (args.extractHtml) {
      result = await page.evaluate((selector) => {
        const elements = Array.from(document.querySelectorAll(selector));
        return elements.map(el => el.outerHTML);
      }, args.selector);
    } else {
      result = await page.evaluate((selector) => {
        const elements = Array.from(document.querySelectorAll(selector));
        return elements.map(el => el.textContent.trim());
      }, args.selector);
    }
  } else {
    if (args.extractHtml) {
      result = await page.content();
    } else {
      result = await page.evaluate(() => document.body.innerText);
    }
  }
  
  await browser.close();
  
  console.log(JSON.stringify({ success: true, content: result }));
})().catch(err => {
  console.error(JSON.stringify({ success: false, error: err.message }));
  process.exit(1);
});
            """)

def handle_action(action, parameters):
    """Handle Puppeteer tool actions according to MCP standard"""
    ensure_script_dir()
    
    action_handlers = {
        "screenshot": take_screenshot,
        "pdf": generate_pdf,
        "extract": extract_content
    }
    
    if action not in action_handlers:
        raise ValueError(f"Unknown action: {action}")
    
    return action_handlers[action](parameters)

def take_screenshot(parameters):
    """Take a screenshot of a webpage"""
    url = parameters.get('url')
    full_page = parameters.get('fullPage', False)
    image_type = parameters.get('type', 'png')
    
    if not url:
        raise ValueError("URL parameter is required")
    
    # Create a temporary file for the screenshot
    with tempfile.NamedTemporaryFile(suffix=f'.{image_type}', delete=False) as tmp_file:
        output_path = tmp_file.name
    
    # Prepare arguments for the Node.js script
    script_args = {
        'url': url,
        'outputPath': output_path,
        'fullPage': full_page,
        'type': image_type,
        'headless': current_app.config.get('PUPPETEER_HEADLESS', True),
        'executablePath': current_app.config.get('CHROME_PATH')
    }
    
    # Add optional parameters if provided
    for param in ['waitForSelector', 'waitTime', 'viewport', 'userAgent', 'quality']:
        if param in parameters:
            script_args[param] = parameters[param]
    
    # Execute the Node.js script
    script_path = SCRIPT_DIR / 'screenshot.js'
    
    try:
        process = subprocess.run(
            ['node', str(script_path), json.dumps(script_args)],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output
        result = json.loads(process.stdout)
        
        # Read the screenshot file
        with open(output_path, 'rb') as f:
            image_data = f.read()
        
        # Encode as base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Clean up the file
        os.unlink(output_path)
        
        return {
            'success': True,
            'imageType': image_type,
            'base64Image': base64_image
        }
    
    except subprocess.CalledProcessError as e:
        # Clean up the file
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        error_message = e.stderr
        try:
            error_data = json.loads(error_message)
            return {
                'success': False,
                'error': error_data.get('error', error_message)
            }
        except:
            return {
                'success': False,
                'error': error_message
            }
    
    except Exception as e:
        # Clean up the file
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        return {
            'success': False,
            'error': str(e)
        }

def generate_pdf(parameters):
    """Generate a PDF of a webpage"""
    url = parameters.get('url')
    print_background = parameters.get('printBackground', True)
    
    if not url:
        raise ValueError("URL parameter is required")
    
    # Create a temporary file for the PDF
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
        output_path = tmp_file.name
    
    # Prepare arguments for the Node.js script
    script_args = {
        'url': url,
        'outputPath': output_path,
        'printBackground': print_background,
        'headless': current_app.config.get('PUPPETEER_HEADLESS', True),
        'executablePath': current_app.config.get('CHROME_PATH')
    }
    
    # Add optional parameters if provided
    for param in ['format', 'margin', 'waitForSelector', 'waitTime', 'viewport', 'userAgent']:
        if param in parameters:
            script_args[param] = parameters[param]
    
    # Execute the Node.js script
    script_path = SCRIPT_DIR / 'pdf.js'
    
    try:
        process = subprocess.run(
            ['node', str(script_path), json.dumps(script_args)],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output
        result = json.loads(process.stdout)
        
        # Read the PDF file
        with open(output_path, 'rb') as f:
            pdf_data = f.read()
        
        # Encode as base64
        base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
        
        # Clean up the file
        os.unlink(output_path)
        
        return {
            'success': True,
            'base64Pdf': base64_pdf
        }
    
    except subprocess.CalledProcessError as e:
        # Clean up the file
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        error_message = e.stderr
        try:
            error_data = json.loads(error_message)
            return {
                'success': False,
                'error': error_data.get('error', error_message)
            }
        except:
            return {
                'success': False,
                'error': error_message
            }
    
    except Exception as e:
        # Clean up the file
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        return {
            'success': False,
            'error': str(e)
        }

def extract_content(parameters):
    """Extract content from a webpage"""
    url = parameters.get('url')
    selector = parameters.get('selector')
    extract_html = parameters.get('extractHtml', False)
    
    if not url:
        raise ValueError("URL parameter is required")
    
    # Prepare arguments for the Node.js script
    script_args = {
        'url': url,
        'selector': selector,
        'extractHtml': extract_html,
        'headless': current_app.config.get('PUPPETEER_HEADLESS', True),
        'executablePath': current_app.config.get('CHROME_PATH')
    }
    
    # Add optional parameters if provided
    for param in ['waitForSelector', 'waitTime', 'userAgent']:
        if param in parameters:
            script_args[param] = parameters[param]
    
    # Execute the Node.js script
    script_path = SCRIPT_DIR / 'extract.js'
    
    try:
        process = subprocess.run(
            ['node', str(script_path), json.dumps(script_args)],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse the output
        result = json.loads(process.stdout)
        
        return {
            'success': True,
            'content': result.get('content')
        }
    
    except subprocess.CalledProcessError as e:
        error_message = e.stderr
        try:
            error_data = json.loads(error_message)
            return {
                'success': False,
                'error': error_data.get('error', error_message)
            }
        except:
            return {
                'success': False,
                'error': error_message
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# API routes for direct access (not through MCP gateway)
@puppeteer_routes.route('/screenshot', methods=['POST'])
def api_screenshot():
    """API endpoint for taking a screenshot"""
    try:
        data = request.get_json()
        result = take_screenshot(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@puppeteer_routes.route('/pdf', methods=['POST'])
def api_pdf():
    """API endpoint for generating a PDF"""
    try:
        data = request.get_json()
        result = generate_pdf(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@puppeteer_routes.route('/extract', methods=['POST'])
def api_extract():
    """API endpoint for extracting content"""
    try:
        data = request.get_json()
        result = extract_content(data)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400