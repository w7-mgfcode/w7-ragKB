#!/bin/bash
rm -rf .hypothesis tests/__pycache__
find tests -name '*.pyc' -delete 2>/dev/null
python -m pytest tests/test_pbt_token_manager.py tests/test_pbt_auth_router.py tests/test_pbt_password_reset.py tests/test_pbt_data_router.py tests/test_pbt_admin_profile.py tests/test_pbt_auto_refresh.py tests/test_pbt_google_oauth.py -v --tb=short -p no:cacheprovider 2>&1 > pbt_results_full.txt
echo "DONE: exit=$?" >> pbt_results_full.txt
