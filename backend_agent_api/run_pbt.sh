#!/bin/bash
python -m pytest tests/test_pbt_token_manager.py tests/test_pbt_auth_router.py tests/test_pbt_password_reset.py tests/test_pbt_data_router.py tests/test_pbt_admin_profile.py tests/test_pbt_auto_refresh.py tests/test_pbt_google_oauth.py -v --tb=short 2>&1 | tee /tmp/pbt_full_results.txt
echo "EXIT_CODE: $?"
