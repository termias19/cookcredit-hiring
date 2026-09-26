import { useLocation, useNavigate } from 'react-router-dom'
import { ChefHat, BriefcaseBusiness, Star, Building2 } from 'lucide-react'
import './HiringBottomNav.css'

export default function HiringBottomNav() {
  const navigate = useNavigate(), { pathname } = useLocation()
  const items = [
    {name:'Candidates', Icon:ChefHat, path:'/business/candidates', active:pathname.startsWith('/business/candidate')},
    {name:'Roles', Icon:BriefcaseBusiness, path:'/business/roles', active:pathname.startsWith('/business/role')},
    {name:'Saved', Icon:Star, path:'/business/shortlists', active:pathname === '/business/shortlists'},
    {name:'Company', Icon:Building2, path:'/business/profile', active:pathname === '/business/profile'},
  ]
  return <nav className="cc-hiring-bottom-nav" aria-label="Hiring navigation">
    {items.map(({name,Icon,path,active}) => <button key={path} type="button" aria-current={active ? 'page' : undefined} onClick={() => navigate(path)}>
      <Icon size={22} strokeWidth={1.6}/><span>{name}</span>
    </button>)}
  </nav>
}
