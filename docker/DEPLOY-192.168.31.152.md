# 复制到 192.168.31.152 后使用（勿提交私钥）

## 1. 在目标机开启 SSH

```bash
# Ubuntu/Debian 示例
sudo apt update && sudo apt install -y openssh-server
sudo systemctl enable --now ssh
sudo ufw allow 22/tcp   # 若启用了 ufw
```

将本机公钥写入 `~/.ssh/authorized_keys`，或使用你提供的密钥对应的公钥。

## 2. 从 Mac 同步代码并部署

```bash
# Mac 上（替换 USER）
rsync -avz --exclude .git --exclude node_modules --exclude '**/.venv' \
  -e "ssh -i /path/to/key" \
  /Users/traceless/AIWork/xiaomi-miloco/ USER@192.168.31.152:~/xiaomi-miloco/

ssh -i /path/to/key USER@192.168.31.152 \
  'cd ~/xiaomi-miloco && bash scripts/deploy-linux-docker.sh'
```

## 3. 复用 Mac 上已有配置（可选）

```bash
rsync -avz -e "ssh -i /path/to/key" \
  /Users/traceless/AIWork/xiaomi-miloco/docker/data/ \
  USER@192.168.31.152:~/xiaomi-miloco/docker/data/
```

## 4. 验证

- `http://192.168.31.152:1810/` 家庭面板
- 米家账号绑定、摄像头需与 **192.168.31.152 同网段**

## 安全提醒

**切勿将 SSH 私钥提交到 Git 或贴在聊天里。** 若私钥已泄露，请在目标机轮换密钥并禁用旧公钥。
