import unittest

from time import sleep
from unittest import TestCase
from redisbloom.client import Client as RedisBloom

xrange = range
rb = None
port = 6379

i = lambda l: [int(v) for v in l]


# Can be used with assertRaises
def run_func(func, *args, **kwargs):
    func(*args, **kwargs)


class TestRedisBloom(TestCase):
    def setUp(self):
        global rb
        rb = RedisBloom(port=port)
        rb.flushdb()

    def testCreate(self):
        '''Test CREATE/RESERVE calls'''
        self.assertTrue(rb.bfCreate('bloom', 0.01, 1000))
        self.assertTrue(rb.bfCreate('bloom_e', 0.01, 1000, expansion=1))
        self.assertTrue(rb.bfCreate('bloom_ns', 0.01, 1000, noScale=True))
        self.assertTrue(rb.cfCreate('cuckoo', 1000))
        self.assertTrue(rb.cfCreate('cuckoo_e', 1000, expansion=1))
        self.assertTrue(rb.cfCreate('cuckoo_bs', 1000, bucket_size=4))
        self.assertTrue(rb.cfCreate('cuckoo_mi', 1000, max_iterations=10))
        self.assertTrue(rb.cmsInitByDim('cmsDim', 100, 5))
        self.assertTrue(rb.cmsInitByProb('cmsProb', 0.01, 0.01))
        self.assertTrue(rb.topkReserve('topk', 5, 100, 5, 0.9))
        self.assertTrue(rb.tdigestCreate('tDigest', 100))

    ################### Test Bloom Filter ###################
    def testBFAdd(self):
        self.assertTrue(rb.bfCreate('bloom', 0.01, 1000))
        self.assertEqual(1, rb.bfAdd('bloom', 'foo'))
        self.assertEqual(0, rb.bfAdd('bloom', 'foo'))
        self.assertEqual([0], i(rb.bfMAdd('bloom', 'foo')))
        self.assertEqual([0, 1], rb.bfMAdd('bloom', 'foo', 'bar'))
        self.assertEqual([0, 0, 1], rb.bfMAdd('bloom', 'foo', 'bar', 'baz'))
        self.assertEqual(1, rb.bfExists('bloom', 'foo'))
        self.assertEqual(0, rb.bfExists('bloom', 'noexist'))
        self.assertEqual([1, 0], i(rb.bfMExists('bloom', 'foo', 'noexist')))

    def testBFInsert(self):
        self.assertTrue(rb.bfCreate('bloom', 0.01, 1000))
        self.assertEqual([1], i(rb.bfInsert('bloom', ['foo'])))
        self.assertEqual([0, 1], i(rb.bfInsert('bloom', ['foo', 'bar'])))
        self.assertEqual([1], i(rb.bfInsert('captest', ['foo'], capacity=1000)))
        self.assertEqual([1], i(rb.bfInsert('errtest', ['foo'], error=0.01)))
        self.assertEqual(1, rb.bfExists('bloom', 'foo'))
        self.assertEqual(0, rb.bfExists('bloom', 'noexist'))
        self.assertEqual([1, 0], i(rb.bfMExists('bloom', 'foo', 'noexist')))
        info = rb.bfInfo('bloom')
        self.assertEqual(2, info.insertedNum)
        self.assertEqual(1000, info.capacity)
        self.assertEqual(1, info.filterNum)

    def testBFDumpLoad(self):
        # Store a filter
        rb.bfCreate('myBloom', '0.0001', '1000')

        # test is probabilistic and might fail. It is OK to change variables if
        # certain to not break anything
        def do_verify():
            res = 0
            for x in xrange(1000):
                rb.bfAdd('myBloom', x)
                rv = rb.bfExists('myBloom', x)
                self.assertTrue(rv)
                rv = rb.bfExists('myBloom', 'nonexist_{}'.format(x))
                res += (rv == x)
            self.assertLess(res, 5)

        do_verify()
        cmds = []
        cur = rb.bfScandump('myBloom', 0)
        first = cur[0]
        cmds.append(cur)

        while True:
            cur = rb.bfScandump('myBloom', first)
            first = cur[0]
            if first == 0:
                break
            else:
                cmds.append(cur)
        prev_info = rb.execute_command('bf.debug', 'myBloom')

        # Remove the filter
        rb.execute_command('del', 'myBloom')

        # Now, load all the commands:
        for cmd in cmds:
            rb.bfLoadChunk('myBloom', *cmd)

        cur_info = rb.execute_command('bf.debug', 'myBloom')
        self.assertEqual(prev_info, cur_info)
        do_verify()

        rb.execute_command('del', 'myBloom')
        rb.bfCreate('myBloom', '0.0001', '10000000')

    def testBFInfo(self):
        expansion = 4
        # Store a filter
        rb.bfCreate('nonscaling', '0.0001', '1000', noScale=True)
        info = rb.bfInfo('nonscaling')
        self.assertEqual(info.expansionRate, None)

        rb.bfCreate('expanding', '0.0001', '1000', expansion=expansion)
        info = rb.bfInfo('expanding')
        self.assertEqual(info.expansionRate, 4)

        try:
            # noScale mean no expansion
            rb.bfCreate('myBloom', '0.0001', '1000', expansion=expansion, noScale=True)
            self.assertTrue(False)
        except:
            self.assertTrue(True)

    ################### Test Cuckoo Filter ###################
    def testCFAddInsert(self):
        self.assertTrue(rb.cfCreate('cuckoo', 1000))
        self.assertTrue(rb.cfAdd('cuckoo', 'filter'))
        self.assertFalse(rb.cfAddNX('cuckoo', 'filter'))
        self.assertEqual(1, rb.cfAddNX('cuckoo', 'newItem'))
        self.assertEqual([1], rb.cfInsert('captest', ['foo']))
        self.assertEqual([1], rb.cfInsert('captest', ['foo'], capacity=1000))
        self.assertEqual([1], rb.cfInsertNX('captest', ['bar']))
        self.assertEqual([1], rb.cfInsertNX('captest', ['food'], nocreate='1'))
        self.assertEqual([0, 0, 1], rb.cfInsertNX('captest', ['foo', 'bar', 'baz']))
        self.assertEqual([0], rb.cfInsertNX('captest', ['bar'], capacity=1000))
        self.assertEqual([1], rb.cfInsert('empty1', ['foo'], capacity=1000))
        self.assertEqual([1], rb.cfInsertNX('empty2', ['bar'], capacity=1000))
        info = rb.cfInfo('captest')
        self.assertEqual(5, info.insertedNum)
        self.assertEqual(0, info.deletedNum)
        self.assertEqual(1, info.filterNum)

    def testCFExistsDel(self):
        self.assertTrue(rb.cfCreate('cuckoo', 1000))
        self.assertTrue(rb.cfAdd('cuckoo', 'filter'))
        self.assertTrue(rb.cfExists('cuckoo', 'filter'))
        self.assertFalse(rb.cfExists('cuckoo', 'notexist'))
        self.assertEqual(1, rb.cfCount('cuckoo', 'filter'))
        self.assertEqual(0, rb.cfCount('cuckoo', 'notexist'))
        self.assertTrue(rb.cfDel('cuckoo', 'filter'))
        self.assertEqual(0, rb.cfCount('cuckoo', 'filter'))

    ################### Test Count-Min Sketch ###################
    def testCMS(self):
        self.assertTrue(rb.cmsInitByDim('dim', 1000, 5))
        self.assertTrue(rb.cmsInitByProb('prob', 0.01, 0.01))
        self.assertTrue(rb.cmsIncrBy('dim', ['foo'], [5]))
        self.assertEqual([0], rb.cmsQuery('dim', 'notexist'))
        self.assertEqual([5], rb.cmsQuery('dim', 'foo'))
        self.assertEqual([10, 15], rb.cmsIncrBy('dim', ['foo', 'bar'], [5, 15]))
        self.assertEqual([10, 15], rb.cmsQuery('dim', 'foo', 'bar'))
        info = rb.cmsInfo('dim')
        self.assertEqual(1000, info.width)
        self.assertEqual(5, info.depth)
        self.assertEqual(25, info.count)

    def testCMSMerge(self):
        self.assertTrue(rb.cmsInitByDim('A', 1000, 5))
        self.assertTrue(rb.cmsInitByDim('B', 1000, 5))
        self.assertTrue(rb.cmsInitByDim('C', 1000, 5))
        self.assertTrue(rb.cmsIncrBy('A', ['foo', 'bar', 'baz'], [5, 3, 9]))
        self.assertTrue(rb.cmsIncrBy('B', ['foo', 'bar', 'baz'], [2, 3, 1]))
        self.assertEqual([5, 3, 9], rb.cmsQuery('A', 'foo', 'bar', 'baz'))
        self.assertEqual([2, 3, 1], rb.cmsQuery('B', 'foo', 'bar', 'baz'))
        self.assertTrue(rb.cmsMerge('C', 2, ['A', 'B']))
        self.assertEqual([7, 6, 10], rb.cmsQuery('C', 'foo', 'bar', 'baz'))
        self.assertTrue(rb.cmsMerge('C', 2, ['A', 'B'], ['1', '2']))
        self.assertEqual([9, 9, 11], rb.cmsQuery('C', 'foo', 'bar', 'baz'))
        self.assertTrue(rb.cmsMerge('C', 2, ['A', 'B'], ['2', '3']))
        self.assertEqual([16, 15, 21], rb.cmsQuery('C', 'foo', 'bar', 'baz'))

    ################### Test Top-K ###################
    def testTopK(self):
        # test list with empty buckets
        self.assertTrue(rb.topkReserve('topk', 3, 50, 4, 0.9))
        self.assertEqual([None, None, None, 'A', 'C', 'D', None, None, 'E',
                          None, 'B', 'C', None, None, None, 'D', None],
                          rb.topkAdd('topk', 'A', 'B', 'C', 'D', 'E', 'A', 'A', 'B', 'C',
                                     'G', 'D', 'B', 'D', 'A', 'E', 'E', 1))
        self.assertEqual([1, 1, 0, 0, 1, 0, 0],
                          rb.topkQuery('topk', 'A', 'B', 'C', 'D', 'E', 'F', 'G'))
        self.assertEqual([4, 3, 2, 3, 3, 0, 1],
                          rb.topkCount('topk', 'A', 'B', 'C', 'D', 'E', 'F', 'G'))

        # test full list
        self.assertTrue(rb.topkReserve('topklist', 3, 50, 3, 0.9))
        self.assertTrue(rb.topkAdd('topklist', 'A', 'B', 'C', 'D', 'E','A', 'A', 'B', 'C',
                                   'G', 'D', 'B', 'D', 'A', 'E', 'E'))
        self.assertEqual(['A', 'B', 'E'], rb.topkList('topklist'))
        self.assertEqual(['A', 4, 'B', 3, 'E', 3], rb.topkListWithCount('topklist'))
        info = rb.topkInfo('topklist')
        self.assertEqual(3, info.k)
        self.assertEqual(50, info.width)
        self.assertEqual(3, info.depth)
        self.assertAlmostEqual(0.9, float(info.decay))

    ################### Test T-Digest ###################
    def testTDigestReset(self):
        self.assertTrue(rb.tdigestCreate('tDigest', 10))
        # reset on empty histogram
        self.assertTrue(rb.tdigestReset('tDigest'))
        # insert data-points into sketch
        self.assertTrue(rb.tdigestAdd('tDigest', list(range(10)), [1.0] * 10))

        self.assertTrue(rb.tdigestReset('tDigest'))
        # assert we have 0 unmerged nodes
        self.assertEqual(0, rb.tdigestInfo('tDigest').unmergedNodes)

    def testTDigestMerge(self):
        self.assertTrue(rb.tdigestCreate('to-tDigest', 10))
        self.assertTrue(rb.tdigestCreate('from-tDigest', 10))
        # insert data-points into sketch
        self.assertTrue(rb.tdigestAdd('from-tDigest', [1.0] * 10, [1.0] * 10))
        self.assertTrue(rb.tdigestAdd('to-tDigest', [2.0] * 10, [10.0] * 10))
        # merge from-tdigest into to-tdigest
        self.assertTrue(rb.tdigestMerge('to-tDigest', 'from-tDigest'))
        # we should now have 110 weight on to-histogram
        info = rb.tdigestInfo('to-tDigest')
        total_weight_to = float(info.mergedWeight) + float(info.unmergedWeight)
        self.assertEqual(110, total_weight_to)

    def testTDigestMinMax(self):
        self.assertTrue(rb.tdigestCreate('tDigest', 100))
        # insert data-points into sketch
        self.assertTrue(rb.tdigestAdd('tDigest', [1, 2, 3], [1.0] * 3))
        # min/max
        self.assertEqual(3, float(rb.tdigestMax('tDigest')))
        self.assertEqual(1, float(rb.tdigestMin('tDigest')))

    def testTDigestQuantile(self):
        self.assertTrue(rb.tdigestCreate('tDigest', 500))
        # insert data-points into sketch
        self.assertTrue(rb.tdigestAdd('tDigest', list([x * 0.01 for x in range(1, 10000)]), [1.0] * 10000))
        # assert min min/max have same result as quantile 0 and 1
        self.assertEqual(
            float(rb.tdigestMax('tDigest')),
            float(rb.tdigestQuantile('tDigest', 1.0)),
        )
        self.assertEqual(
            float(rb.tdigestMin('tDigest')),
            float(rb.tdigestQuantile('tDigest', 0.0)),
        )

        self.assertAlmostEqual(1.0, float(rb.tdigestQuantile('tDigest', 0.01)), 2)
        self.assertAlmostEqual(99.0, float(rb.tdigestQuantile('tDigest', 0.99)), 2)

    def testTDigestCdf(self):
        self.assertTrue(rb.tdigestCreate('tDigest', 100))
        # insert data-points into sketch
        self.assertTrue(rb.tdigestAdd('tDigest', list(range(1, 10)), [1.0] * 10))

        self.assertAlmostEqual(0.1, float(rb.tdigestCdf('tDigest', 1.0)), 1)
        self.assertAlmostEqual(0.9, float(rb.tdigestCdf('tDigest', 9.0)), 1)

    def test_pipeline(self):
        pipeline = rb.pipeline()

        self.assertFalse(rb.execute_command('get pipeline'))

        self.assertTrue(rb.bfCreate('pipeline', 0.01, 1000))
        for i in range(100):
            pipeline.bfAdd('pipeline', i)
        for i in range(100):
            self.assertFalse(rb.bfExists('pipeline', i))

        pipeline.execute()

        for i in range(100):
            self.assertTrue(rb.bfExists('pipeline', i))


if __name__ == '__main__':
    unittest.main()
