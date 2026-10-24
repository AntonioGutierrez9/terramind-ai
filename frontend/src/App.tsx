import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout, { ProjectLayout } from './components/Layout'
import { AppProviders } from './state'
import Portfolio from './pages/Portfolio'
import NewProject from './pages/NewProject'
import Usage from './pages/Usage'
import Property from './pages/project/Property'
import Design from './pages/project/Design'
import Market from './pages/project/Market'
import Budget from './pages/project/Budget'
import Financing from './pages/project/Financing'
import Model from './pages/project/Model'
import Sustainability from './pages/project/Sustainability'
import Committee from './pages/project/Committee'
import Asset from './pages/project/Asset'
import Assumptions from './pages/project/Assumptions'
import History from './pages/project/History'

export default function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Portfolio />} />
            <Route path="new" element={<NewProject />} />
            <Route path="usage" element={<Usage />} />
            <Route path="p/:pid" element={<ProjectLayout />}>
              <Route index element={<Navigate to="model" replace />} />
              <Route path="property" element={<Property />} />
              <Route path="design" element={<Design />} />
              <Route path="market" element={<Market />} />
              <Route path="budget" element={<Budget />} />
              <Route path="financing" element={<Financing />} />
              <Route path="model" element={<Model />} />
              <Route path="sustainability" element={<Sustainability />} />
              <Route path="committee" element={<Committee />} />
              <Route path="asset" element={<Asset />} />
              <Route path="assumptions" element={<Assumptions />} />
              <Route path="history" element={<History />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}
