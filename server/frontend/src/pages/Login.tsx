import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import service from '@/api/request';
import { setToken, setUser, type UserInfo } from '@/utils/storage';

/**
 * 登录页：用户名 + 密码 + 角色下拉
 */
export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'submitter' | 'approver'>('submitter');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !password.trim()) {
      setError('请填写用户名和密码');
      return;
    }
    setLoading(true);
    try {
      // 与后端约定的登录接口
      const resp = await service.post<{ token: string; user: UserInfo }>(
        '/auth/login',
        { username, password, role },
      );
      const { token, user } = resp.data;
      setToken(token);
      setUser(user);
      navigate('/documents', { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-100 to-indigo-50">
      <div className="w-[420px] card">
        <div className="card-header">
          <div className="card-title">登录 · 企业智能审批平台</div>
          <div className="mt-1 text-xs text-slate-500">
            请输入账号密码以继续
          </div>
        </div>
        <form className="card-body space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="label">用户名</label>
            <input
              className="input"
              placeholder="请输入用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
            />
          </div>
          <div>
            <label className="label">密码</label>
            <input
              className="input"
              type="password"
              placeholder="请输入密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div>
            <label className="label">角色</label>
            <select
              className="select"
              value={role}
              onChange={(e) => setRole(e.target.value as 'submitter' | 'approver')}
            >
              <option value="submitter">提交人</option>
              <option value="approver">审批人</option>
            </select>
          </div>

          {error && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </div>
          )}

          <button className="btn-primary w-full" disabled={loading}>
            {loading ? '登录中…' : '登 录'}
          </button>
        </form>
      </div>
    </div>
  );
}
