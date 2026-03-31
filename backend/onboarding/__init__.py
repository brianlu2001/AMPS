"""
Buyer onboarding pipeline for AMPS.

Pipeline stages (each in its own module):
  1. instruction_parser  — parse the buyer's natural-language instruction
  2. ingestion           — fetch and normalize URL content
  3. profile_extractor   — extract structured profile fields from content
  4. enrollment          — assemble BuyerProfile, persist, emit log

Entry point: enrollment.run_onboarding(instruction, url, user_id)
"""
