import { useLocation, useNavigate } from 'react-router-dom'
import { ChefHat, BriefcaseBusiness, Settings } from 'lucide-react'
import './HiringBottomNav.css'
import { useLang } from '../context/LangContext'

export default function HiringBottomNav() {
  const navigate = useNavigate(), { pathname } = useLocation()
  const { t } = useLang()
  const items = [
    {name:t.bn_roles, Icon:BriefcaseBusiness, path:'/business/roles', active:pathname.startsWith('/business/role')},
    {name:t.bn_applicants, Icon:ChefHat, path:'/business/candidates', active:pathname.startsWith('/business/candidate')},
    {name:t.bn_settings, Icon:Settings, path:'/business/profile', active:pathname === '/business/profile'},
  ]
  return <nav className="cc-hiring-bottom-nav" aria-label="Hiring navigation">
    {items.map(({name,Icon,path,active}) => <button key={path} type="button" aria-current={active ? 'page' : undefined} onClick={() => navigate(path)}>
      <Icon size={22} strokeWidth={1.6}/><span>{name}</span>
    </button>)}
  </nav>
}
