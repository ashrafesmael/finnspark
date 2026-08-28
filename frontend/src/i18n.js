const dict = {
  en: {
    dashboard: 'Home', announcements: 'Announcements', selections: 'Selection Board',
    forms: 'Forms', programs: 'Programs', courses: 'Courses', library: 'Library',
    investmentForms: 'Investment Forms', dealflow: 'Dealflow', approval: 'Approval',
    portfolio: 'Portfolio Management', reports: 'Reports', calendar: 'Calendar',
    directories: 'Directories', chat: 'Chat', users: 'Users & Roles', organizations: 'Organizations',
    help: 'Help Center', logout: 'Log out', search: 'Search…', create: 'Create', save: 'Save',
    cancel: 'Cancel', edit: 'Edit', delete: 'Delete', exportExcel: 'Export to Excel',
    status: 'Status', actions: 'Actions', program: 'Program', stage: 'Stage', score: 'Avg. Score',
  },
  ar: {
    dashboard: 'الرئيسية', announcements: 'الإعلانات', selections: 'لجنة الاختيار',
    forms: 'النماذج', programs: 'البرامج', courses: 'الدورات', library: 'المكتبة',
    investmentForms: 'نماذج الاستثمار', dealflow: 'تدفق الصفقات', approval: 'الاعتماد',
    portfolio: 'إدارة المحفظة', reports: 'التقارير', calendar: 'التقويم',
    directories: 'الأدلة', chat: 'المحادثة', users: 'المستخدمون والأدوار', organizations: 'المنظمات',
    help: 'مركز المساعدة', logout: 'تسجيل الخروج', search: 'بحث…', create: 'إنشاء', save: 'حفظ',
    cancel: 'إلغاء', edit: 'تعديل', delete: 'حذف', exportExcel: 'تصدير إلى Excel',
    status: 'الحالة', actions: 'إجراءات', program: 'البرنامج', stage: 'المرحلة', score: 'المعدل',
  },
}

export const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'ar', label: 'العربية' },
]

let lang = localStorage.getItem('vaLang') || 'en'
export const getLang = () => lang
export const setLang = (l) => {
  lang = l
  localStorage.setItem('vaLang', l)
  document.documentElement.dir = l === 'ar' ? 'rtl' : 'ltr'
}
document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'

export const t = (key) => dict[lang]?.[key] ?? dict.en[key] ?? key
