"""
LLM Handler Module
Manages interaction with Groq API for quotation generation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import Config
from groq import Groq
from typing import Dict, Any, Optional
import json


class LLMHandler:
    """Handle Groq LLM API interactions for quotation generation"""
    
    def __init__(self):
        """
        Initialize LLM handler — reads API key from Config.
        """
        self.api_key = Config.GROQ_API_KEY
        self.client = Groq(api_key=Config.GROQ_API_KEY)
        self.model = "llama-3.3-70b-versatile"  # Updated to current supported model
    
    def create_quotation_prompt(self, requirements: str, template_type: str, company_name: str = "Your Company") -> str:
        """
        Build prompt for LLM to generate quotation
        
        Args:
            requirements: Extracted requirements text
            template_type: 'type1' or 'type2'
            company_name: Name of the company creating the quotation
            
        Returns:
            Formatted prompt string
        """
        
        if template_type == 'type1':
            template_instructions = """
Generate a COMPREHENSIVE DETAILED PROPOSAL (4-5 pages) with the following structure:

1. **Project Title**
   - Extract or create a clear, professional title for the proposal

2. **Scope of Work/Deliverables** (MOST IMPORTANT - BE VERY DETAILED)
   - CAREFULLY READ the requirements and extract EVERY SINGLE deliverable mentioned
   - You MUST list 12-15 numbered items minimum (match the detail level in requirements)
   - For each item, provide:
     * A clear title
     * Detailed description with bullet points
     * Include ALL sub-tasks and technical details mentioned
   - Format as "Title: Description with sub-bullets"
   - DO NOT summarize - include ALL deliverables from the requirements

3. **Commercials (Pricing Table)**
   Create a pricing table with:
   - Service Description (detailed)
   - Fees (INR)
   
   Include 5-6 service line items with realistic INR pricing.
   Each pricing item should correspond to major deliverable groups.

4. **Terms & Notes** (CRITICAL - BE COMPREHENSIVE)
   Generate 9-10 detailed terms covering:
   - License/subscription details
   - Client responsibilities (credentials, access, etc.)
   - Revision policy
   - Training details
   - Support duration and scope
   - Timeline and completion criteria
   - Payment terms
   - Third-party integration costs
   - Content/data requirements
   - Any project-specific conditions from requirements
   
   Make these specific to the project requirements, not generic.

5. **Bank Details for Payment**
   - Provide realistic Indian bank details
   - Include: Bank Name, Account Name, Account Number, IFSC Code, MICR Code

CRITICAL: This must be a COMPLETE, DETAILED proposal spanning 4-5 pages. Extract EVERY detail from the requirements.
"""
        else:  # type2
            template_instructions = """
Generate an EXECUTIVE SUMMARY STYLE QUOTATION (2-3 pages) with the following structure:

1. **Cover Page Content**
   - Project title
   - Client name
   - Date
   - Reference number

2. **Executive Overview** (2-3 paragraphs)
   - Business challenge/opportunity
   - Proposed solution approach
   - Expected outcomes

3. **Solution Package**
   - Package name and description
   - Key features included
   - Main deliverables (consolidated, not itemized)

4. **Investment Summary Table**
   Create a clean table with:
   - Package Component
   - Description
   - Investment
   
   Include 4-6 major components.

5. **Implementation Approach** (1-2 paragraphs)
   - Methodology
   - Timeline overview
   - Key phases

6. **Value Proposition**
   - Benefits to client
   - ROI considerations
   - Success metrics

7. **Next Steps**
   - Acceptance process
   - Project kickoff timeline
   - Contact information

Make this polished and executive-focused, spanning 2-3 pages when formatted.
"""
        
        prompt = f"""You are a professional business proposal writer. Based on the following client requirements, create a comprehensive quotation proposal.

**Client Requirements:**
{requirements}

**Template Type:** {template_type.upper()}

{template_instructions}

**IMPORTANT INSTRUCTIONS:**
- Generate REALISTIC and DETAILED content (2-3 pages worth)
- All pricing should be in INR (Indian Rupees)
- Use professional business language
- Include specific technical details based on requirements
- Make tables comprehensive with multiple rows
- Ensure all sections are well-developed, not just placeholders
- Return the response in JSON format with the following structure:

{{
    "project_title": "string",
    "client_name": "string (extract from requirements if available, else use 'Valued Client')",
    "date": "string (use current date format: DD/MM/YYYY)",
    "reference_number": "string (generate a professional reference like QT-2024-001)",
    "pan_number": "string (generate realistic PAN like AGVPJ1503G)",
    "gstin": "string (generate realistic GSTIN like 27AGVPJ1503G1ZF)",
    "proposal_validity": "string (date 30 days from now in format: DDth Month YYYY)",
    "authorized_signatory_name": "string (e.g., Ms. Mili Juneja)",
    "company_name": "string (default: MJ Services)",
    "company_role": "string (e.g., Authorized Zoho Channel Partner)",
    "bank_name": "string (realistic Indian bank name)",
    "account_name": "string (account holder name)",
    "account_number": "string (realistic account number)",
    "ifsc_code": "string (realistic IFSC code)",
    "micr_code": "string (realistic MICR code)",
    "executive_summary": "string (detailed paragraph)",
    "scope_of_work": ["array of detailed scope items"],
    "pricing_table": [
        {{
            "item_no": "string",
            "description": "string",
            "quantity": "string",
            "unit_price": "string",
            "total_price": "string"
        }}
    ],
    "timeline": [
        {{
            "phase": "string",
            "duration": "string",
            "deliverables": "string"
        }}
    ],
    "terms_and_conditions": ["array of terms"],
    "subtotal": "string",
    "tax": "string",
    "grand_total": "string",
    "additional_notes": "string"
}}

Generate a complete, professional quotation now.
"""
        
        return prompt
    
    def generate_quotation(self, requirements: str, template_type: str, company_name: str = "Your Company") -> Dict[str, Any]:
        """
        Generate quotation using Groq LLM
        
        Args:
            requirements: Extracted requirements text
            template_type: 'type1' or 'type2'
            company_name: Company name for quotation
            
        Returns:
            Dictionary containing quotation data
        """
        try:
            prompt = self.create_quotation_prompt(requirements, template_type, company_name)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional business proposal writer specializing in creating detailed, comprehensive quotations. Always return valid JSON responses."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=4000,
                top_p=1,
                stream=False
            )
            
            # Extract response
            llm_response = response.choices[0].message.content
            
            # Parse JSON response
            quotation_data = self._parse_llm_response(llm_response)
            quotation_data['template_type'] = template_type
            quotation_data['success'] = True
            
            return quotation_data
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'template_type': template_type
            }
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response and extract quotation data
        
        Args:
            response: Raw LLM response string
            
        Returns:
            Structured quotation data
        """
        try:
            # Try to parse as JSON
            # Remove markdown code blocks if present
            cleaned_response = response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.startswith('```'):
                cleaned_response = cleaned_response[3:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            cleaned_response = cleaned_response.strip()
            
            data = json.loads(cleaned_response)
            return data
            
        except json.JSONDecodeError:
            # If JSON parsing fails, create a basic structure
            return {
                'project_title': 'Project Quotation',
                'client_name': 'Valued Client',
                'date': 'Current Date',
                'reference_number': 'QT-2024-001',
                'executive_summary': response[:500],
                'scope_of_work': ['Please review the generated content'],
                'pricing_table': [],
                'timeline': [],
                'terms_and_conditions': [],
                'subtotal': 'TBD',
                'tax': 'TBD',
                'grand_total': 'TBD',
                'additional_notes': 'Raw response: ' + response
            }
