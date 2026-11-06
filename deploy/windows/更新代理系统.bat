@echo off
chcp 65001 >nul
title 更新代理管理系统
echo 正在连接学校服务器，更新代理管理系统……
echo （只更新已经合并到仓库 main 的版本；服务器重启后系统会锁定，更新完请登录一次）
echo.
set KEY=%USERPROFILE%\.ssh\ja-server-polo
set OPTS=-i "%KEY%" -o HostKeyAlias=192.168.1.72 -o ConnectTimeout=10
ssh %OPTS% polo@192.168.1.75 "bash ~/agent-portal/deploy/server/update.sh"
if errorlevel 255 (
  echo.
  echo USB 有线网卡 .75 连不上，改用 Wi-Fi .73 再试一次……
  ssh %OPTS% polo@192.168.1.73 "bash ~/agent-portal/deploy/server/update.sh"
)
echo.
echo 看到「部署完成」和「合同自检：通过」就是更新成功；看到「部署失败」请把这个窗口截图发给 Claude。
pause
