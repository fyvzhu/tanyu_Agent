import request from '@/utils/request'

/**
 * 获取商品列表
 */
export function getProducts(params) {
  return request({
    url: '/commerce/api/v1/catalog/products',
    method: 'get',
    params,
  })
}

/**
 * 获取商品详情
 */
export function getProductDetail(productId) {
  return request({
    url: `/commerce/api/v1/catalog/products/${productId}`,
    method: 'get',
  })
}

/**
 * 获取订单列表
 */
export function getOrders(params) {
  return request({
    url: '/commerce/api/v1/orders',
    method: 'get',
    params,
  })
}

/**
 * 获取订单详情
 */
export function getOrderDetail(orderId) {
  return request({
    url: `/commerce/api/v1/orders/${orderId}`,
    method: 'get',
  })
}

/**
 * 转换图片路径（添加 /commerce 前缀）
 */
export function transformImageUrl(url) {
  if (!url) return ''
  if (url.startsWith('http')) return url
  if (url.startsWith('/static/')) {
    return `/commerce${url}`
  }
  return url
}
