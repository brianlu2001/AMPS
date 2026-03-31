"""
Seller onboarding pipeline for AMPS.

Pipeline stages (each in its own module):
  1. validation    — validate the registration request fields
  2. profile_builder — assemble a SellerProfile from validated input
  3. review_trigger  — queue the new seller for auditor review
  4. registration    — persist profile, register agent, emit log

Entry point: registration.run_seller_registration(request, user_id, store, registry)
"""
