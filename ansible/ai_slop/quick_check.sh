#!/bin/bash

# Quick diagnostic check for NextDraw API 502 errors
# Run this on the Raspberry Pi to quickly diagnose issues

echo "NextDraw API Quick Diagnostic Check"
echo "==================================="
echo

# Check service status
echo "1. Service Status:"
echo -n "   - nextdraw-api: "
systemctl is-active nextdraw-api || echo " (NOT RUNNING)"
echo -n "   - nginx: "
systemctl is-active nginx || echo " (NOT RUNNING)"
echo

# Check if Flask is listening
echo "2. Port Check:"
echo -n "   - Port 5000: "
sudo netstat -tlnp | grep -q ":5000" && echo "LISTENING" || echo "NOT LISTENING"
echo

# Quick API test
echo "3. API Tests:"
echo -n "   - Direct API (http://localhost:5000/health): "
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000/health 2>/dev/null || echo "FAILED"
echo
echo -n "   - Through Nginx (http://localhost/health): "
curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "FAILED"
echo
echo

# Show recent errors
echo "4. Recent Errors:"
echo "   Service logs:"
sudo journalctl -u nextdraw-api -n 5 --no-pager | grep -E "(ERROR|error|Error)" || echo "   No recent errors"
echo

# Quick fix attempt
echo "5. Quick Fix Commands:"
echo "   sudo systemctl restart nextdraw-api"
echo "   sudo systemctl restart nginx"
echo
read -p "Run quick fix commands? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl restart nextdraw-api
    sudo systemctl restart nginx
    sleep 3
    echo
    echo "Services restarted. Testing again..."
    echo -n "API Status: "
    curl -s -o /dev/null -w "%{http_code}" http://localhost/health 2>/dev/null || echo "FAILED"
    echo
fi

echo
echo "For detailed troubleshooting, run: sudo /tmp/troubleshoot_502.sh"
