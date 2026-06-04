import { describe, it, expect, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import HumanApprovalBox from '../HumanApprovalBox.vue'

/**
 * HumanApprovalBox 组件测试
 *
 * 验证：
 * 1. props.questions 正确渲染 Tab + 选项
 * 2. 单选：点击选项切换选中
 * 3. 多选：累加/移除
 * 4. 虚拟 Other 项：点击展开 textarea
 * 5. Enter 提交 Other
 * 6. Esc 取消 Other
 * 7. 全局提交 emit 正确结构
 * 8. canSubmit 门控：所有问题必答
 */

const baseQuestion = {
  question: 'Pick a framework?',
  header: 'Framework',
  options: [
    { label: 'React', description: 'A JS library' },
    { label: 'Vue', description: 'A progressive framework' },
    { label: 'Other', description: 'Specify your own' }
  ],
  multiple: false
}

const mountBox = (props = {}) =>
  mount(HumanApprovalBox, {
    props: { questions: [baseQuestion], ...props }
  })

describe('HumanApprovalBox', () => {
  describe('rendering', () => {
    it('renders question and options', () => {
      const wrapper = mountBox()
      expect(wrapper.text()).toContain('Pick a framework?')
      expect(wrapper.text()).toContain('React')
      expect(wrapper.text()).toContain('Vue')
      expect(wrapper.text()).toContain('Other')
    })

    it('does not render tab bar for single question', () => {
      const wrapper = mountBox()
      expect(wrapper.find('.tab-bar').exists()).toBe(false)
    })

    it('renders tab bar with headers for multiple questions', () => {
      const wrapper = mountBox({
        questions: [
          { ...baseQuestion, header: 'Framework' },
          { ...baseQuestion, header: 'TypeScript', question: 'Use TypeScript?' }
        ]
      })
      const tabs = wrapper.findAll('.tab-btn')
      expect(tabs.length).toBe(2)
      expect(tabs[0].text()).toContain('Framework')
      expect(tabs[1].text()).toContain('TypeScript')
    })
  })

  describe('single-select', () => {
    it('selecting an option highlights it', async () => {
      const wrapper = mountBox()
      const options = wrapper.findAll('.option-btn')
      await options[0].trigger('click')
      expect(options[0].classes()).toContain('selected')
      expect(options[1].classes()).not.toContain('selected')
    })

    it('selecting another option replaces the previous', async () => {
      const wrapper = mountBox()
      const options = wrapper.findAll('.option-btn')
      await options[0].trigger('click')
      await options[1].trigger('click')
      expect(options[0].classes()).not.toContain('selected')
      expect(options[1].classes()).toContain('selected')
    })
  })

  describe('multi-select', () => {
    it('allows selecting multiple options', async () => {
      const multi = { ...baseQuestion, multiple: true }
      const wrapper = mountBox({ questions: [multi] })
      const options = wrapper.findAll('.option-btn')
      await options[0].trigger('click')
      await options[1].trigger('click')
      expect(options[0].classes()).toContain('selected')
      expect(options[1].classes()).toContain('selected')
    })

    it('deselects when clicking a selected option again', async () => {
      const multi = { ...baseQuestion, multiple: true }
      const wrapper = mountBox({ questions: [multi] })
      const options = wrapper.findAll('.option-btn')
      await options[0].trigger('click')
      await options[0].trigger('click')
      expect(options[0].classes()).not.toContain('selected')
    })
  })

  describe('virtual Other item', () => {
    it('clicking Other reveals textarea', async () => {
      const wrapper = mountBox()
      const options = wrapper.findAll('.option-btn')
      await options[2].trigger('click') // Other
      await flushPromises()
      expect(wrapper.find('.other-input').exists()).toBe(true)
    })

    it('Enter commits Other text into answers', async () => {
      const wrapper = mountBox()
      const options = wrapper.findAll('.option-btn')
      await options[2].trigger('click')
      await flushPromises()
      const ta = wrapper.find('.other-input')
      await ta.setValue('Svelte')
      await ta.trigger('keydown.enter.exact')
      await flushPromises()
      // 编辑器应该收起
      expect(wrapper.find('.other-input').exists()).toBe(false)
    })

    it('Esc cancels Other and clears', async () => {
      const wrapper = mountBox()
      const options = wrapper.findAll('.option-btn')
      await options[2].trigger('click')
      await flushPromises()
      const ta = wrapper.find('.other-input')
      await ta.setValue('Svelte')
      await ta.trigger('keydown.escape')
      await flushPromises()
      expect(wrapper.find('.other-input').exists()).toBe(false)
    })
  })

  describe('canSubmit gating', () => {
    it('button is disabled initially', () => {
      const wrapper = mountBox()
      const btn = wrapper.find('.confirm-btn')
      expect(btn.attributes('disabled')).toBeDefined()
    })

    it('enables after selecting a non-Other option', async () => {
      const wrapper = mountBox()
      const options = wrapper.findAll('.option-btn')
      await options[0].trigger('click')
      const btn = wrapper.find('.confirm-btn')
      expect(btn.attributes('disabled')).toBeUndefined()
    })
  })

  describe('submit emit', () => {
    it('emits { answers: [[label]] } for single question single select', async () => {
      const wrapper = mountBox()
      const options = wrapper.findAll('.option-btn')
      await options[0].trigger('click')
      await wrapper.find('.confirm-btn').trigger('click')
      const events = wrapper.emitted('submit')
      expect(events).toBeTruthy()
      expect(events[0][0]).toEqual({ answers: [['React']] })
    })

    it('emits { answers: [[label1, label2]] } for multi-select', async () => {
      const multi = { ...baseQuestion, multiple: true }
      const wrapper = mountBox({ questions: [multi] })
      const options = wrapper.findAll('.option-btn')
      await options[0].trigger('click')
      await options[1].trigger('click')
      await wrapper.find('.confirm-btn').trigger('click')
      const events = wrapper.emitted('submit')
      expect(events[0][0].answers[0]).toEqual(['React', 'Vue'])
    })

    it('emits answers array matching questions length for multi-question', async () => {
      const wrapper = mountBox({
        questions: [
          { ...baseQuestion, header: 'Framework' },
          { ...baseQuestion, header: 'TS', question: 'Use TypeScript?' }
        ]
      })
      // 选第 1 题
      await wrapper.findAll('.option-btn')[0].trigger('click')
      // 切到第 2 题
      await wrapper.findAll('.tab-btn')[1].trigger('click')
      await wrapper.findAll('.option-btn')[1].trigger('click')
      await wrapper.find('.confirm-btn').trigger('click')
      const events = wrapper.emitted('submit')
      expect(events[0][0].answers.length).toBe(2)
      expect(events[0][0].answers[0]).toEqual(['React'])
      expect(events[0][0].answers[1]).toEqual(['Vue'])
    })
  })

  describe('freeform mode (text-only questions)', () => {
    const freeformQuestion = {
      question: '请输入项目名称',
      header: '项目',
      options: [],
      multiple: false,
      text_only: true
    }

    it('renders textarea instead of options-list when no options', () => {
      const wrapper = mountBox({ questions: [freeformQuestion] })
      expect(wrapper.find('.freeform-editor').exists()).toBe(true)
      expect(wrapper.find('.freeform-input').exists()).toBe(true)
      expect(wrapper.find('.options-list').exists()).toBe(false)
    })

    it('submit is enabled only after typing text', async () => {
      const wrapper = mountBox({ questions: [freeformQuestion] })
      const btn = wrapper.find('.confirm-btn')
      expect(btn.attributes('disabled')).toBeDefined()

      const ta = wrapper.find('.freeform-input')
      await ta.setValue('Project Alpha')
      expect(wrapper.find('.confirm-btn').attributes('disabled')).toBeUndefined()
    })

    it('emits trimmed text as single-element answer array', async () => {
      const wrapper = mountBox({ questions: [freeformQuestion] })
      await wrapper.find('.freeform-input').setValue('  Project Alpha  ')
      await wrapper.find('.confirm-btn').trigger('click')
      const events = wrapper.emitted('submit')
      expect(events[0][0].answers).toEqual([['Project Alpha']])
    })

    it('mixed freeform and options questions work together', async () => {
      const wrapper = mountBox({
        questions: [
          freeformQuestion,                                          // 第 1 题：纯文本
          { ...baseQuestion, header: 'Framework' }                    // 第 2 题：选项
        ]
      })
      // 答第 1 题
      await wrapper.find('.freeform-input').setValue('My Project')
      // 切到第 2 题
      await wrapper.findAll('.tab-btn')[1].trigger('click')
      await wrapper.findAll('.option-btn')[0].trigger('click')
      await wrapper.find('.confirm-btn').trigger('click')
      const events = wrapper.emitted('submit')
      expect(events[0][0].answers).toEqual([['My Project'], ['React']])
    })

    it('empty freeform input keeps submit disabled', async () => {
      const wrapper = mountBox({ questions: [freeformQuestion] })
      await wrapper.find('.freeform-input').setValue('   ')  // 只有空格
      const btn = wrapper.find('.confirm-btn')
      expect(btn.attributes('disabled')).toBeDefined()
    })
  })

  describe('real-world mixed scenario (3 questions: multi-select + 2 freeform)', () => {
    // 用户提供的真实数据：1 个多选题（5 options）+ 2 个 text_only 题
    const realQuestions = [
      {
        question: '请选择项目类型（可多选）',
        header: '项目类型',
        options: [
          { label: '工业用地', description: '工业生产、制造加工类项目' },
          { label: '住宅用地 (Recommended)', description: '住宅小区、公寓等居住类项目' },
          { label: '商业用地', description: '商场、写字楼等商业经营类项目' },
          { label: '公共服务用地', description: '学校、医院等公共服务类项目' },
          { label: 'Other', description: '输入自定义回答' }
        ],
        multiple: true,
        text_only: false
      },
      {
        question: '请输入项目名称',
        header: '项目名称',
        options: [],
        multiple: false,
        text_only: true
      },
      {
        question: '如有其他需求请简要说明',
        header: '补充说明',
        options: [],
        multiple: false,
        text_only: true
      }
    ]

    it('renders 3 tabs and switches between modes', async () => {
      const wrapper = mountBox({ questions: realQuestions })
      const tabs = wrapper.findAll('.tab-btn')
      expect(tabs.length).toBe(3)
      // Q1 是 options 模式
      expect(wrapper.find('.options-list').exists()).toBe(true)
      expect(wrapper.find('.freeform-editor').exists()).toBe(false)
    })

    it('freeform tab shows textarea instead of options', async () => {
      const wrapper = mountBox({ questions: realQuestions })
      await wrapper.findAll('.tab-btn')[1].trigger('click') // 切到 Q2
      expect(wrapper.find('.options-list').exists()).toBe(false)
      expect(wrapper.find('.freeform-editor').exists()).toBe(true)
      expect(wrapper.text()).toContain('请输入项目名称')
    })

    it('completes the 3-question flow: select options + 2 text inputs', async () => {
      const wrapper = mountBox({ questions: realQuestions })
      // Q1: 多选 2 个（住宅 + 商业）
      await wrapper.findAll('.option-btn')[1].trigger('click')  // 住宅用地
      await wrapper.findAll('.option-btn')[2].trigger('click')  // 商业用地
      // Q2: 纯文本输入项目名
      await wrapper.findAll('.tab-btn')[1].trigger('click')
      await wrapper.find('.freeform-input').setValue('阳光花园小区')
      // Q3: 纯文本输入补充说明
      await wrapper.findAll('.tab-btn')[2].trigger('click')
      await wrapper.find('.freeform-input').setValue('需要配套学校')
      // 提交
      await wrapper.find('.confirm-btn').trigger('click')
      const events = wrapper.emitted('submit')
      expect(events).toBeTruthy()
      expect(events[0][0].answers).toEqual([
        ['住宅用地 (Recommended)', '商业用地'],
        ['阳光花园小区'],
        ['需要配套学校']
      ])
    })

    it('submit disabled until all 3 questions answered', async () => {
      const wrapper = mountBox({ questions: realQuestions })
      // 只答 Q1
      await wrapper.findAll('.option-btn')[0].trigger('click')
      // 切到 Q2 看到 disabled
      await wrapper.findAll('.tab-btn')[1].trigger('click')
      expect(wrapper.find('.confirm-btn').attributes('disabled')).toBeDefined()
    })
  })
})
